"""Exercise workflow wiring with real policy/CLI code and in-memory Actions/cloud fakes."""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
import unittest
from unittest.mock import patch

import yaml

from ci import online_shop as ci

ROOT = Path(__file__).resolve().parents[1]


class WorkflowHarness:
    def __init__(self, root):
        self.root = root
        self.workflows = {name: yaml.safe_load((ROOT / '.github/workflows' / name).read_text())
                          for name in ('request-runner.yml', 'build-and-push.yml')}
        self.artifacts = {}
        self.capacity_requests = []
        self.cloud_ready = True
        self.operations = []
        self.active_runs = []
        self.runner_labels = []

    def job(self, workflow, job, run_id, event, attempt=1):
        definition = self.workflows[workflow]['jobs'][job]
        labels = definition['runs-on']
        if labels.startswith('${{'):
            # Evaluate the workflow's routing expression, not a duplicate policy constant.
            expression = re.fullmatch(
                r'''\$\{\{ github.run_attempt == 1 && fromJSON\('(.+)'\) \|\| '([^']+)' \}\}''', labels)
            if not expression:
                raise AssertionError('unrecognized runner routing')
            labels = json.loads(expression[1]) if attempt == 1 else expression[2]
        self.runner_labels.append(labels)
        directory = self.root / f'{workflow}-{job}-{run_id}-{attempt}'
        directory.mkdir()
        output = directory / 'outputs'
        event_file = directory / 'event.json'
        ci.write(event_file, event)
        env = dict(GITHUB_REPOSITORY=ci.CI_REPOSITORY, GITHUB_RUN_ID=str(run_id),
                   GITHUB_RUN_ATTEMPT=str(attempt), GITHUB_SHA='a' * 40,
                   GITHUB_WORKFLOW_SHA='a' * 40,
                   GITHUB_WORKFLOW_REF=ci.CI_REPOSITORY + '/.github/workflows/' + workflow + '@refs/heads/main',
                   GITHUB_EVENT_NAME='workflow_dispatch' if job == 'request-runner' else 'workflow_run',
                   GITHUB_EVENT_PATH=str(event_file), GITHUB_OUTPUT=str(output),
                   GH_READ_TOKEN='fake-read-token', DISPATCH_INPUTS='{}')
        outputs = {}

        def expand(value):
            value = str(value).replace('$RUNNER_TEMP', str(directory)).replace('${{ runner.temp }}', str(directory))
            value = value.replace('${{ github.event.workflow_run.id }}', str(event.get('workflow_run', {}).get('id', '')))
            value = value.replace('${{ github.run_id }}', str(run_id)).replace('${{ github.run_attempt }}', str(attempt))
            for key, val in outputs.items():
                value = value.replace('${{ steps.policy.outputs.' + key + ' }}', val)
            return value

        for step in definition['steps']:
            # This harness runs the sample route so it can exercise the full handoff offline.
            if "== 'online-shop'" in step.get('if', ''):
                continue
            action = step.get('uses', '').split('@')[0]
            command = step.get('run', '')
            if 'ci/online_shop.py' in command:
                if ' policy ' in command and 'if' in step:
                    raise AssertionError('policy must run unconditionally after checkout')
                args = shlex.split(command.replace('"$RUNNER_TEMP', '"' + str(directory)))
                args = [expand(arg) for arg in args[2:]]
                self.operations.append(args[0])
                with patch.dict(os.environ, env, clear=True), patch('sys.argv', ['online_shop.py'] + args), \
                        patch.object(ci, 'github_runs', return_value=self.active_runs):
                    ci.main()
                if output.exists():
                    outputs.update(line.split('=', 1) for line in output.read_text().splitlines())
            elif action == 'actions/upload-artifact':
                self.operations.append('upload')
                source = Path(expand(step['with']['path']))
                self.artifacts[run_id, expand(step['with']['name'])] = {
                    p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
            elif action == 'actions/download-artifact':
                self.operations.append('download')
                source_run = int(expand(step['with'].get('run-id', run_id)))
                artifact = self.artifacts[source_run, expand(step['with']['name'])]
                destination = Path(expand(step['with']['path']))
                destination.mkdir(exist_ok=True)
                for name, data in artifact.items():
                    (destination / name).write_bytes(data)
            elif 'curl ' in command:
                self.operations.append('capacity')
                if not self.cloud_ready:
                    raise RuntimeError('fake capacity unavailable; operator must restore lifecycle readiness')
                self.capacity_requests.append(run_id)
            elif 'docker build ' in command:
                self.operations.append('sample-build')
            elif action == 'docker/login-action':
                self.operations.append('registry-login')
        return outputs


class WorkflowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.h = WorkflowHarness(Path(self.temp.name))
        self.event = dict(repository=dict(default_branch='main'), workflow_run=dict(
            repository=dict(full_name=ci.CI_REPOSITORY), head_repository=dict(full_name=ci.CI_REPOSITORY),
            event='workflow_dispatch', conclusion='success', path='.github/workflows/request-runner.yml',
            id=10, run_attempt=1, head_sha='a' * 40, head_branch='main'))

    def request(self, run_id=10, attempt=1):
        return self.h.job('request-runner.yml', 'request-runner', run_id, {}, attempt)

    def handoff(self, run_id=20, attempt=1, event=None):
        return self.h.job('build-and-push.yml', 'handoff', run_id, event or self.event, attempt)

    def build(self, run_id=20, attempt=1, event=None):
        return self.h.job('build-and-push.yml', 'build', run_id, event or self.event, attempt)

    def test_original_chain_uses_exact_artifact_and_capacity(self):
        self.request()
        self.handoff()
        self.build()
        self.assertEqual(self.h.capacity_requests, [10])
        self.assertIn('sample-build', self.h.operations)
        self.assertEqual(self.h.runner_labels[-1], ['self-hosted', 'gce', 'ephemeral'])
        self.assertIn((10, 'build-request-10-1'), self.h.artifacts)
        self.assertIn((20, 'validated-request-20-1'), self.h.artifacts)

    def test_missing_or_mismatched_handoff_fails_on_hosted(self):
        with self.assertRaises(KeyError):
            self.handoff()
        self.request()
        name = (10, 'build-request-10-1')
        request = json.loads(self.h.artifacts[name]['request.json'])
        request['request']['runId'] = 99
        self.h.artifacts[name]['request.json'] = ci.encoded(request)
        with self.assertRaisesRegex(ValueError, 'correlation mismatch'):
            self.handoff(run_id=21)
        self.assertTrue(all(labels == 'ubuntu-latest' for labels in self.h.runner_labels))

    def test_previous_attempt_artifact_is_never_used(self):
        self.request()
        self.h.artifacts[10, 'build-request-10-0'] = self.h.artifacts.pop((10, 'build-request-10-1'))
        with self.assertRaises(KeyError):
            self.handoff()
        old_request = copy.deepcopy(self.event)
        old_request['workflow_run']['run_attempt'] = 2
        with self.assertRaisesRegex(ValueError, 'Rerun request'):
            self.handoff(run_id=21, event=old_request)

    def test_request_rerun_does_not_request_capacity_or_upload(self):
        self.request()
        before = self.h.operations.copy()
        with self.assertRaisesRegex(ValueError, 'reruns are unsupported'):
            self.request(attempt=2)
        self.assertEqual(self.h.operations[len(before):], ['policy'])
        self.assertEqual(self.h.capacity_requests, [10])

    def test_full_consumer_rerun_rejected_before_download(self):
        self.request()
        self.handoff()
        before = self.h.operations.copy()
        with self.assertRaisesRegex(ValueError, 'reruns are unsupported'):
            self.handoff(attempt=2)
        self.assertEqual(self.h.operations[len(before):], ['policy'])
        self.assertEqual(self.h.runner_labels[-1], 'ubuntu-latest')

    def test_partial_build_rerun_rejects_even_with_cached_handoff(self):
        self.request()
        self.handoff()
        # Only the failed build job reruns; attempt-1 handoff remains successful.
        before = self.h.operations.copy()
        with self.assertRaisesRegex(ValueError, 'reruns are unsupported'):
            self.build(attempt=2)
        self.assertEqual(self.h.operations[len(before):], ['policy'])
        self.assertEqual(self.h.runner_labels[-1], 'ubuntu-latest')
        self.assertNotIn((20, 'validated-request-20-2'), self.h.artifacts)

    def test_fresh_dispatch_recovers_with_new_capacity_after_exit(self):
        self.request()
        self.handoff()
        self.build()
        self.h.active_runs = [dict(id=20, status='completed')]
        self.h.cloud_ready = False  # Existing stopped VM does not imply restart readiness.
        with self.assertRaisesRegex(RuntimeError, 'capacity unavailable'):
            self.request(run_id=11)
        self.h.cloud_ready = True  # Operator has restored startup/registration prerequisites.
        self.request(run_id=12)
        event = copy.deepcopy(self.event)
        event['workflow_run']['id'] = 12
        self.handoff(run_id=22, event=event)
        self.build(run_id=22, event=event)
        self.assertEqual(self.h.capacity_requests, [10, 12])

    def test_visible_overlap_rejected_and_requests_cannot_exchange_inputs(self):
        self.h.active_runs = [dict(id=9, status='in_progress')]
        with self.assertRaisesRegex(ValueError, 'Another runner request/build is active'):
            self.request()
        self.assertEqual(self.h.capacity_requests, [])
        self.h.active_runs = []
        self.request(run_id=11)
        # An unrelated valid artifact cannot satisfy the exact run-bound lookup.
        with self.assertRaises(KeyError):
            self.handoff()
        self.h.artifacts[10, 'build-request-10-1'] = self.h.artifacts[11, 'build-request-11-1']
        with self.assertRaisesRegex(ValueError, 'correlation mismatch'):
            self.handoff(run_id=21)

    def test_capacity_check_paginates_and_fails_closed(self):
        calls = []
        def fake(workflow, page):
            calls.append((workflow, page))
            return [dict(id=1, status='completed')] * 100 if page == 1 else [dict(id=2, status='queued')]
        with self.assertRaisesRegex(ValueError, 'Another runner request/build is active'):
            ci.check_capacity_window('10', fake)
        self.assertEqual(calls, [('request-runner.yml', 1), ('request-runner.yml', 2)])
        with self.assertRaises(OSError):
            ci.check_capacity_window('10', lambda *_: (_ for _ in ()).throw(OSError('fake GitHub failure')))


if __name__ == '__main__':
    unittest.main()
