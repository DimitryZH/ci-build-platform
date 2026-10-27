import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import online_shop as ci

REVISION = '87c39c498ebf4b7f9b7347f7b317aae27a0630f3'


class ProducerTests(unittest.TestCase):
    def setUp(self):
        self.inputs = dict(build_kind='online-shop', source_revision=REVISION,
                           components='frontend', platform='linux/amd64', build_arguments='[]')
        self.reference = dict(repository=ci.CI_REPOSITORY, runId=10, attempt=2,
                              toolingRevision='a' * 40, workflowRevision='a' * 40,
                              workflowRef=ci.CI_REPOSITORY + '/.github/workflows/request-runner.yml@refs/heads/main')
        self.event = dict(repository=dict(default_branch='main'), workflow_run=dict(
            repository=dict(full_name=ci.CI_REPOSITORY), head_repository=dict(full_name=ci.CI_REPOSITORY),
            event='workflow_dispatch', conclusion='success', path='.github/workflows/request-runner.yml',
            id=10, run_attempt=2, head_sha='a' * 40, head_branch='main'))
        self.data = dict(requestVersion=1, request=self.reference, selection=ci.selection(self.inputs))
        self.plan = dict(planVersion=1, contractVersion=1, repository=ci.REPOSITORY,
                         sourceRevision=REVISION, toolingRevision=REVISION, workloadPath=ci.WORKLOAD,
                         platform='linux/amd64', components=[dict(id='frontend', buildContext='src/frontend',
                         dockerfile='src/frontend/Dockerfile', target=None, preparation=[],
                         buildArguments=dict(SOURCE_REVISION=REVISION, SKAFFOLD_GO_GCFLAGS='all=-N -l'))])
        self.data.update(plan=self.plan, planSha256=ci.sha(ci.encoded(self.plan)),
                         destinations=dict(frontend='docker.io/dmitryzhuravlev/online-shop-frontend'),
                         contractSha256=ci.sha(b'contract'))

    def test_routes_and_invalid_inputs(self):
        self.assertEqual(ci.selection({})['kind'], 'sample')
        self.assertEqual(ci.selection(self.inputs)['components'], ['frontend'])
        for updates in [dict(source_revision='main'), dict(source_revision=REVISION.upper()),
                        dict(components=''), dict(components='frontend frontend'), dict(components='../frontend'),
                        dict(platform='linux/arm64'), dict(build_kind='other'),
                        dict(build_arguments='{}'), dict(build_arguments='[1]'),
                        dict(build_arguments='["frontend.X=x\\ny"]'),
                        dict(build_kind='sample')]:
            with self.subTest(updates=updates), self.assertRaises((ValueError, TypeError)):
                ci.selection(self.inputs | updates)

    def test_correlation_and_retries(self):
        self.assertEqual(ci.correlate(self.data, self.event)['kind'], 'online-shop')
        sample = ci.envelope({}, self.reference)
        self.assertEqual(ci.correlate(sample, self.event)['kind'], 'sample')
        for field, value in [('id', 11), ('run_attempt', 1), ('head_sha', 'b' * 40),
                             ('head_branch', 'feature'), ('event', 'push'), ('conclusion', 'failure'),
                             ('head_repository', dict(full_name='attacker/repo'))]:
            event = copy.deepcopy(self.event)
            event['workflow_run'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                ci.correlate(self.data, event)
        with self.assertRaises(KeyError):
            ci.correlate({}, self.event)
        modified = copy.deepcopy(self.data)
        modified['plan']['platform'] = 'linux/arm64'
        with self.assertRaises(ValueError):
            ci.correlate(modified, self.event)

    def test_argument_array_and_target(self):
        c = self.plan['components'][0]
        command = ci.build_command(self.plan, c, 'example:tag')
        self.assertIn('SKAFFOLD_GO_GCFLAGS=all=-N -l', command)
        self.assertNotIn('--target', command)
        c['target'] = 'final'
        self.assertEqual(ci.build_command(self.plan, c, 'tag')[10:12], ['--target', 'final'])
        for path in ['../escape', '/abs', 'a/../b', 'C:/abs', 'a\\b']:
            with self.assertRaises(ValueError):
                ci.safe_path(path)

    def exercise_publication(self, fail=None):
        image = dict(Id='sha256:' + 'c' * 64, Os='linux', Architecture='amd64',
                     Config=dict(Labels={'org.opencontainers.image.revision': REVISION}))
        calls = []
        class Registry:
            def __init__(self, repository):
                self.count = 0
            def manifest(self, reference):
                self.count += 1
                if fail == 'registry':
                    raise OSError('unavailable')
                if self.count == 1:
                    return ('existing', {}) if fail == 'collision' else None
                if fail == 'missing':
                    return None
                if fail == 'index':
                    return 'sha256:' + 'd' * 64, dict(schemaVersion=2, manifests=[])
                return 'sha256:' + 'd' * 64, dict(schemaVersion=2, config=dict(digest=image['Id']))
        def execute(command, cwd=None):
            calls.append(command)
            if command[1] == fail or (command[1:3] == ['buildx', 'build'] and fail == 'build'):
                raise RuntimeError('fake operation failure')
            if command[1:3] == ['image', 'inspect']:
                result = copy.deepcopy(image)
                if '@' in command[-1] and fail == 'label':
                    result['Config']['Labels']['org.opencontainers.image.revision'] = 'wrong'
                if '@' in command[-1] and fail == 'platform':
                    result['Architecture'] = 'arm64'
                return json.dumps([result]).encode()
            return b''
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            (root / ci.WORKLOAD).mkdir(parents=True)
            (root / ci.WORKLOAD / 'build.contract.json').write_bytes(b'contract')
            output = root / 'output'
            output.mkdir()
            with patch.object(ci, 'prepare', return_value=(self.plan, self.data['destinations'])):
                if fail:
                    with self.assertRaises((ValueError, RuntimeError, OSError)):
                        ci.publish(root, self.data, self.reference | dict(runId=20, attempt=3), output, execute, Registry)
                    self.assertEqual(list(output.glob('*.result.json')), [])
                else:
                    ci.publish(root, self.data, self.reference | dict(runId=20, attempt=3), output, execute, Registry)
                    result = json.loads((output / 'frontend.result.json').read_bytes())
                    self.assertEqual(result['buildResultVersion'], 1)
                    self.assertIn('q10a2-b20a3', result['image']['tag'])
                    self.assertEqual(result['image']['manifestDigest'], 'sha256:' + 'd' * 64)
                    self.assertNotEqual(result['image']['localImageId'], result['image']['manifestDigest'])
                    self.assertIsNone(result['image']['indexDigest'])
                    self.assertEqual(result['sourceRevision'], REVISION)
                    self.assertEqual(result['build']['toolingRevision'], 'a' * 40)
                    self.assertTrue(any(c[1] == 'pull' and '@sha256:' in c[-1] for c in calls))

    def test_successful_metadata(self):
        self.exercise_publication()

    def test_failures_never_emit_success(self):
        for failure in ['build', 'push', 'pull', 'registry', 'collision', 'missing', 'index', 'label', 'platform']:
            with self.subTest(failure=failure):
                self.exercise_publication(failure)

    def test_source_bytes_and_hidden_artifacts(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            ci.run(['git', 'init', str(root)])
            ci.git(root, 'config', 'core.autocrlf', 'false')
            (root / ci.WORKLOAD).mkdir(parents=True)
            source = root / ci.WORKLOAD / 'source.txt'
            source.write_bytes(b'hello\n')
            ci.git(root, 'add', '.')
            ci.git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'test: source')
            revision = ci.git(root, 'rev-parse', 'HEAD').decode().strip()
            ci.verify_checkout(root, revision)
            source.write_bytes(b'hello\r\n')
            with self.assertRaises(ValueError):
                ci.verify_checkout(root, revision)
            source.write_bytes(b'hello\n')
            (root / ci.WORKLOAD / 'extra').write_bytes(b'undeclared')
            with self.assertRaises(ValueError):
                ci.verify_checkout(root, revision)

    def test_plan_consumption_and_hash_rejection(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            workload = root / ci.WORKLOAD
            (workload / 'src/frontend').mkdir(parents=True)
            dockerfile = workload / 'src/frontend/Dockerfile'
            dockerfile.write_bytes(b'FROM scratch\n')
            component = self.plan['components'][0]
            component.update(inputs=[dict(path=component['dockerfile'], sha256=ci.sha(dockerfile.read_bytes()))],
                             dockerfileSha256=ci.sha(dockerfile.read_bytes()))
            ci.write(workload / 'fake-plan.json', self.plan)
            (workload / 'build_plan.py').write_text(
                'import json\nfrom pathlib import Path\n'
                'def plan(root, *args):\n'
                '    return json.loads((Path(root) / "workloads/online-shop/fake-plan.json").read_bytes())\n')
            ci.write(workload / 'images.lock.json', dict(components=[dict(id='frontend', sourcePath='src/frontend',
                     image=dict(repository=self.data['destinations']['frontend']))]))
            with patch.object(ci, 'verify_checkout'):
                plan, destinations = ci.prepare(root, self.data['selection'])
                self.assertEqual(plan, self.plan)
                self.assertEqual(destinations, self.data['destinations'])
                dockerfile.write_bytes(b'FROM malicious\n')
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    ci.prepare(root, self.data['selection'])
                dockerfile.write_bytes(b'FROM scratch\n')
                ci.write(workload / 'images.lock.json', dict(components=[dict(id='frontend', sourcePath='src/frontend',
                         image=dict(repository='docker.io/other/online-shop-frontend'))]))
                with self.assertRaisesRegex(ValueError, 'namespace'):
                    ci.prepare(root, self.data['selection'])


if __name__ == '__main__':
    unittest.main()
