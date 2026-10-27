"""Plan-driven Online Shop producer. Python 3.10+, Git and Docker CLI."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
REPOSITORY = 'https://github.com/DimitryZH/application-modernization-lab'
CI_REPOSITORY = 'DimitryZH/ci-build-platform'
WORKLOAD = 'workloads/online-shop'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def write(path, value):
    Path(path).write_bytes(encoded(value))


def run(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, stderr=subprocess.PIPE)


def git(root, *args):
    return run(['git', '-C', str(root), *args])


def selection(inputs):
    mode = inputs.get('build_kind', 'sample')
    require(mode in ('sample', 'online-shop'), 'unknown build kind')
    revision = inputs.get('source_revision', '')
    components = inputs.get('components', '').split()
    platform = inputs.get('platform', 'linux/amd64')
    arguments = json.loads(inputs.get('build_arguments', '[]'))
    require(isinstance(arguments, list) and all(isinstance(x, str) for x in arguments),
            'build_arguments must be a JSON array of strings')
    require(platform == 'linux/amd64', 'unsupported platform')
    if mode == 'sample':
        require(not revision and not components and not arguments, 'sample cannot consume AML inputs')
    else:
        require(re.fullmatch('[0-9a-f]{40}', revision), 'full lowercase commit SHA required')
        require(components and len(components) == len(set(components)) and
                all(re.fullmatch('[a-z][a-z0-9]*', c) for c in components), 'invalid component selection')
    require(all(re.fullmatch(r'[a-z][a-z0-9]*\.[A-Z_][A-Z_0-9]*=[^\r\n\x00]*', a)
                    for a in arguments), 'invalid component-qualified argument')
    return dict(kind=mode, sourceRevision=revision, components=sorted(components),
                platform=platform, buildArguments=arguments)


def identity(env):
    return dict(repository=env['GITHUB_REPOSITORY'], runId=int(env['GITHUB_RUN_ID']),
                url='https://github.com/' + env['GITHUB_REPOSITORY'] + '/actions/runs/' + env['GITHUB_RUN_ID'],
                attempt=int(env['GITHUB_RUN_ATTEMPT']), toolingRevision=env['GITHUB_SHA'],
                workflowRevision=env['GITHUB_WORKFLOW_SHA'], workflowRef=env['GITHUB_WORKFLOW_REF'])


def execution_policy(env, phase, event=None):
    """Only fresh dispatch chains may consume the singleton ephemeral capacity."""
    require(env['GITHUB_RUN_ATTEMPT'] == '1',
            'Workflow/job reruns are unsupported; verify cleanup and capacity, then create a fresh manual request')
    run_id = env['GITHUB_RUN_ID']
    require(re.fullmatch('[1-9][0-9]*', run_id), 'invalid run ID')
    if phase == 'request':
        require(env['GITHUB_EVENT_NAME'] == 'workflow_dispatch', 'manual request required')
        return dict(request_artifact=f'build-request-{run_id}-1')
    require(phase in ('handoff', 'build') and env['GITHUB_EVENT_NAME'] == 'workflow_run',
            'invalid consumer phase/event')
    trigger = event['workflow_run']
    require(type(trigger['run_attempt']) is int and trigger['run_attempt'] == 1,
            'Rerun request attempts are unsupported; create a fresh manual request')
    require(type(trigger['id']) is int and trigger['id'] > 0, 'invalid request run ID')
    return dict(request_artifact=f"build-request-{trigger['id']}-1",
                validated_artifact=f'validated-request-{run_id}-1')


def github_runs(workflow, page, token):
    url = (f'https://api.github.com/repos/{CI_REPOSITORY}/actions/workflows/{workflow}/runs'
           f'?per_page=100&page={page}')
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
                                                 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)['workflow_runs']


def check_capacity_window(run_id, fetch_runs):
    """Reject visible overlapping chains; operators still serialize the singleton."""
    for workflow in ('request-runner.yml', 'build-and-push.yml'):
        page = 1
        while True:
            runs = fetch_runs(workflow, page)
            require(all(r['id'] == int(run_id) or r['status'] == 'completed' for r in runs),
                    'Another runner request/build is active; wait for the whole chain and VM cleanup before a fresh dispatch')
            if len(runs) < 100:
                break
            page += 1


def materialize(root, revision):
    require(not root.exists(), 'source directory must be new')
    run(['git', 'init', str(root)])
    git(root, 'config', 'core.autocrlf', 'false')
    git(root, 'config', 'core.hooksPath', '/dev/null')
    git(root, 'remote', 'add', 'origin', REPOSITORY + '.git')
    git(root, 'fetch', '--depth=1', 'origin', revision)
    git(root, '-c', 'core.autocrlf=false', 'checkout', '--detach', 'FETCH_HEAD')
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == revision, 'checkout HEAD mismatch')
    verify_checkout(root, revision)


def safe_path(value):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value,
            'invalid plan path')
    p = PurePosixPath(value)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == value, 'unsafe plan path')
    return value


def verify_checkout(root, revision):
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == revision, 'source HEAD mismatch')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all', '--ignored').strip(),
            'source checkout must be clean, including ignored files')
    # Git status normalizes text; compare actual bytes, including the planner itself.
    entries = []
    for row in git(root, 'ls-tree', '-rz', revision, '--', WORKLOAD).split(b'\0'):
        if not row:
            continue
        metadata, name = row.split(b'\t')
        mode, kind, oid = metadata.decode().split()
        require(mode in ('100644', '100755') and kind == 'blob', 'non-regular workload input')
        entries.append((name, oid))
    batch = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'],
                           input=''.join(oid + '\n' for _, oid in entries).encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
    offset = 0
    for name, oid in entries:
        end = batch.index(b'\n', offset)
        size = int(batch[offset:end].split()[2])
        blob = batch[end + 1:end + 1 + size]
        offset = end + size + 2
        path = root / name.decode()
        require(not path.is_symlink() and path.read_bytes() == blob,
                'checkout bytes differ from Git blob: ' + name.decode())


def prepare(root, request):
    revision = request['sourceRevision']
    verify_checkout(root, revision)
    planner = root / WORKLOAD / 'build_plan.py'
    spec = importlib.util.spec_from_file_location('aml_plan', planner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = module.plan(root, revision, request['components'], request['platform'], request['buildArguments'])
    require(plan['planVersion'] == 1 and plan['contractVersion'] == 1 and
            plan['repository'] == REPOSITORY and plan['workloadPath'] == WORKLOAD and
            plan['sourceRevision'] == revision and plan['toolingRevision'] == revision and
            plan['platform'] == request['platform'], 'unsupported or mismatched plan identity')
    require(sorted(c['id'] for c in plan['components']) == request['components'], 'plan selection mismatch')
    mapping = json.loads((root / WORKLOAD / 'images.lock.json').read_bytes())
    destinations = {}
    for c in plan['components']:
        for key in ('buildContext', 'dockerfile'):
            safe_path(c[key])
        require(not c['preparation'] and c['buildArguments']['SOURCE_REVISION'] == revision,
                'unsupported preparation or revision')
        for item in c['inputs'] + [dict(path=c['dockerfile'], sha256=c['dockerfileSha256'])]:
            path = root / WORKLOAD / safe_path(item['path'])
            require(sha(path.read_bytes()) == item['sha256'], 'planner input hash mismatch')
        matches = [x for x in mapping['components'] if x['id'] == c['id'] and x['sourcePath']]
        require(len(matches) == 1, 'ambiguous image mapping')
        destination = matches[0]['image']['repository']
        require(re.fullmatch('docker.io/dmitryzhuravlev/online-shop-[a-z0-9]+', destination),
                'destination outside allowed namespace')
        destinations[c['id']] = destination
    return plan, destinations


def envelope(inputs, reference, root=None):
    request = selection(inputs)
    require(reference['repository'] == CI_REPOSITORY, 'wrong request repository')
    result = dict(requestVersion=1, request=reference, selection=request)
    if request['kind'] == 'online-shop':
        plan, destinations = prepare(root, request)
        result.update(plan=plan, planSha256=sha(encoded(plan)), destinations=destinations,
                      contractSha256=sha((root / WORKLOAD / 'build.contract.json').read_bytes()))
    return result


def correlate(data, event):
    trigger = event['workflow_run']
    reference = data['request']
    require(data['requestVersion'] == 1 and reference['repository'] == CI_REPOSITORY and
            trigger['repository']['full_name'] == CI_REPOSITORY and
            trigger['head_repository']['full_name'] == CI_REPOSITORY and
            trigger['event'] == 'workflow_dispatch' and trigger['conclusion'] == 'success' and
            trigger['path'] == '.github/workflows/request-runner.yml', 'untrusted request run')
    require(reference['runId'] == trigger['id'] and reference['attempt'] == trigger['run_attempt'] and
            reference['toolingRevision'] == trigger['head_sha'] and
            reference['workflowRevision'] == trigger['head_sha'], 'request correlation mismatch')
    require(trigger['head_branch'] == event['repository']['default_branch'], 'request must use default branch')
    s = data['selection']
    normalized = selection(dict(build_kind=s['kind'], source_revision=s['sourceRevision'],
                               components=' '.join(s['components']), platform=s['platform'],
                               build_arguments=json.dumps(s['buildArguments'])))
    require(normalized == s, 'noncanonical selection')
    if s['kind'] == 'online-shop':
        require(sha(encoded(data['plan'])) == data['planSha256'], 'handoff plan hash mismatch')
    return s


class Registry:
    """Read public Docker Hub manifests directly; only 404 means an unused tag."""
    def __init__(self, repository):
        self.name = repository.removeprefix('docker.io/')
        query = 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + self.name + ':pull'
        with urllib.request.urlopen(query, timeout=30) as response:
            self.token = json.load(response)['token']

    def manifest(self, reference):
        request = urllib.request.Request('https://registry-1.docker.io/v2/' + self.name + '/manifests/' + reference,
            headers={'Authorization': 'Bearer ' + self.token,
                     'Accept': 'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                digest = 'sha256:' + sha(raw)
                require(response.headers.get('Docker-Content-Digest') == digest, 'registry digest mismatch')
                return digest, json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise


def build_command(plan, component, tag, metadata=None):
    command = ['docker', 'buildx', 'build', '--load', '--platform', plan['platform'], '-t', tag,
               '-f', WORKLOAD + '/' + safe_path(component['dockerfile'])]
    if metadata is not None:
        command += ['--metadata-file', str(metadata)]
    if component['target'] is not None:
        command += ['--target', component['target']]
    for key, value in sorted(component['buildArguments'].items()):
        command += ['--build-arg', key + '=' + value]
    return command + [WORKLOAD + '/' + safe_path(component['buildContext'])]


def _publish(root, data, build, output, execute, registry_factory):
    plan, destinations = prepare(root, data['selection'])
    require(plan == data['plan'] and destinations == data['destinations'] and
            sha(encoded(plan)) == data['planSha256'] and
            sha((root / WORKLOAD / 'build.contract.json').read_bytes()) == data['contractSha256'],
            'recomputed plan/contract differs from request')
    request = data['request']
    for c in plan['components']:
        repository = destinations[c['id']]
        tag = (f"sha-{plan['sourceRevision']}-q{request['runId']}a{request['attempt']}"
               f"-b{build['runId']}a{build['attempt']}")
        registry = registry_factory(repository)
        require(registry.manifest(tag) is None, 'publication identity already exists; create a fresh manual request')
        full_tag = repository + ':' + tag
        metadata = (output / (c['id'] + '.buildx.json')).resolve()
        require(not metadata.exists(), 'build metadata path must be new')
        execute(build_command(plan, c, full_tag, metadata), cwd=root)
        built = json.loads(metadata.read_bytes()).get('containerimage.config.digest')
        require(isinstance(built, str) and re.fullmatch('sha256:[0-9a-f]{64}', built),
                'missing/invalid Buildx config digest for single-platform load')
        local = json.loads(execute(['docker', 'image', 'inspect', full_tag]))[0]['Id']
        require(local == built, 'loaded local image ID differs from Buildx config digest')
        execute(['docker', 'push', full_tag])
        published = registry.manifest(tag)
        require(published is not None, 'published manifest missing')
        digest, manifest = published
        require(manifest.get('schemaVersion') == 2 and 'config' in manifest and 'manifests' not in manifest,
                'expected a single image manifest, not an index')
        require(manifest['config'].get('digest') == local,
                'published manifest config digest differs from built local image ID')
        require(registry.manifest(digest) == published, 'manifest not retrievable by digest')
        immutable = repository + '@' + digest
        execute(['docker', 'pull', '--platform', plan['platform'], immutable])
        image = json.loads(execute(['docker', 'image', 'inspect', immutable]))[0]
        require(image['Os'] + '/' + image['Architecture'] == plan['platform'] and
                image['Config']['Labels'].get('org.opencontainers.image.revision') == plan['sourceRevision'],
                'published platform/source label mismatch')
        require(image['Id'] == manifest['config']['digest'] == local == built,
                'retrieved image ID differs from manifest config/built local image ID')
        result = dict(buildResultVersion=1, status='published-and-verified', componentId=c['id'],
                      sourceRepository=REPOSITORY, sourceRevision=plan['sourceRevision'], workloadPath=WORKLOAD,
                      contract=dict(version=plan['contractVersion'], path=WORKLOAD + '/build.contract.json',
                                    sha256=data['contractSha256']), planSha256=data['planSha256'],
                      buildContext=c['buildContext'], dockerfile=c['dockerfile'], target=c['target'],
                      effectiveArguments=c['buildArguments'], platform=plan['platform'], request=request, build=build,
                      image=dict(repository=repository, tag=tag, manifestDigest=digest, indexDigest=None,
                                 localImageId=local, configDigest=image['Id']))
        write(output / (c['id'] + '.result.json'), result)


def record_failure(output, error):
    write(output / 'failure.json', dict(status='failed', errorType=type(error).__name__,
          diagnostic=str(error) if isinstance(error, ValueError)
          else 'Inspect operation and restricted infrastructure logs'))


def publish(root, data, build, output, execute=run, registry_factory=Registry):
    try:
        _publish(root, data, build, output, execute, registry_factory)
    except Exception as error:
        record_failure(output, error)
        raise


def logged_executor(output):
    counter = 0

    def execute(command, cwd=None):
        nonlocal counter
        counter += 1
        # Docker commands contain only public image identities and validated arguments.
        process = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (output / f'docker-{counter}.log').write_bytes(process.stdout + process.stderr)
        require(process.returncode == 0, f'Docker operation {counter} failed; see retained log')
        return process.stdout

    return execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['policy', 'request', 'validate', 'build'])
    parser.add_argument('--phase', choices=['request', 'handoff', 'build'])
    parser.add_argument('--handoff', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.operation == 'policy':
        event = (json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
                 if args.phase != 'request' else None)
        outputs = execution_policy(os.environ, args.phase, event)
        if args.phase == 'request':
            check_capacity_window(os.environ['GITHUB_RUN_ID'],
                                  lambda workflow, page: github_runs(workflow, page, os.environ['GH_READ_TOKEN']))
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            for key, value in outputs.items():
                stream.write(key + '=' + value + '\n')
        return
    require(args.handoff is not None, '--handoff is required')
    if args.operation == 'request':
        execution_policy(os.environ, 'request')
        inputs = json.loads(os.environ['DISPATCH_INPUTS'])
        request = selection(inputs)
        if request['kind'] == 'online-shop':
            materialize(args.source, request['sourceRevision'])
        data = envelope(inputs, identity(os.environ), args.source)
        args.handoff.parent.mkdir(parents=True, exist_ok=True)
        write(args.handoff, data)
        if 'plan' in data:
            write(args.handoff.parent / 'plan.json', data['plan'])
    else:
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
        execution_policy(os.environ, 'build' if args.operation == 'build' else 'handoff', event)
        data = json.loads(args.handoff.read_bytes())
        request = correlate(data, event)
        if args.operation == 'validate':
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                stream.write('kind=' + request['kind'] + '\n')
        elif request['kind'] == 'online-shop':
            args.output.mkdir(parents=True, exist_ok=False)
            write(args.output / 'plan.json', data['plan'])
            try:
                materialize(args.source, request['sourceRevision'])
                publish(args.source, data, identity(os.environ), args.output,
                        execute=logged_executor(args.output))
            except Exception as error:
                record_failure(args.output, error)
                raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Never echo subprocess stderr: controller URLs or credential-bearing output may occur.
        print('Online Shop operation failed: ' + (str(error) if isinstance(error, ValueError)
                                                  else type(error).__name__), file=sys.stderr)
        sys.exit(1)
