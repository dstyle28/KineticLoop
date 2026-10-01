# HG036 binds only the unstarted KL047 offline infrastructure definition.
# Future scope/semantic changes require separate governance; historical unrefined
# protected bases retain their original packet and are never relabelled.
FITNESS_EVAL_DEFINITION_DIGESTS = {'milestone': '956e5e3d52c685ebc9a545a52bd240ce4d7e92668ff76877175183aa9889a2b3',
 'title': '69e481dc5f1f6dfe073d5af9c36848d0c93057f4b73fae510f2d747538660cc6',
 'owner_role': 'ff610fb106a3a1c1cedcc6589f563a9a1da99b391e061593d0965d58ddaddceb',
 'depends_on': '3107e2f79968e3c2d35593c65c714af842d89b0097e827afa9045ae54f7336d0',
 'commands': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'transaction_boundaries': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'invariant_ids': '283710e28c0d02b671756b1c42e250fad3f32deb19679291eb7be50a1497a92c',
 'table_ids': '9a332a5ddd9c278ae54601ec2de7b3a56a656fd493698a6c6f8d5f0a37d2a65f',
 'required_test_layers': '4b42aa23b42b3ca743449b544cc16ccb8e8ec8cfd2ddcf2f62a9fac0c5760f71',
 'deliverables': '571c2148a82fcaa4fff8e80ec8a6a522f69466cb2dfa587876e467e18266308d',
 'definition_of_done': '8235f87e93611a7323d079198263d3c00797af5073c5ecfe2baee50082ab42b6',
 'entry_conditions': 'cdb8e9e5f374da25bbf860253cfe03aebb468d1bfa3c5814ab3a7de0f62e5d11',
 'thread_mode': 'e08931b96108d4d7b09720df6852f99d68e4b39207dca0c1cbab878221a358d4',
 'context_files': '32248e7aa59b56fc871aaf7f9db803fa7752ba0bfe609d644405a073a54bf4c0',
 'max_context_policy': '146220a2aa769d8163fb894618fe689e8aa94a7a4240418735beeb016306660c',
 'merge_unit': '48f009959aa958b4b832ed0ce7af1e468160c0fae875bb5592b63882743e92d6',
 'handoff_artifact': '1a5914ada8e642eebf033f0ca1addfd6274734a39c370097848884866f60b77a',
 'shared_hotspot': 'fcbcf165908dd18a9e49f7ff27810176db8e9f63b4352213741664245224f8aa',
 'parallel_write_policy': '18673037cf4a790bffe39b043258e1c9ad8de9c40878e9739555fa5551a6e773',
 'task_identity': '3418099843e2fcd2528596625e8908d22a49baddebbcb18db366756f23d6e13b',
 'requirements_covered': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'checks_required_for_this_task': '18ebe2f6b730574e34bbd90f1166ecc1e1ec212ebb9cf14db0c9a5fa58ad6160',
 'resource_keys': 'd4105520a414172165c6490416c291fd56c26aea511c2126daec93529eef2f33',
 'write_paths': 'f9fe4dabe8eb6718cceb0df885c48dacd15a0c89d77b3c19842834bba570d3df',
 'review_requirements': '0469d2acfb8a5ec7a8beb4e1a047624a8371744c73f975a708080a1c32135964',
 'conditional_depends_on': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'environment_requirements': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'packet_refinement': 'bf90cfa6d2424aaea97cbc7342a33d90a3022ac6e104ade780cabd2d598818ad',
 'required_test_layers_semantics': 'a9a68d6f7dd868aa585d451f7591de3871f0b1608c2bdc84292071f167412d9f',
 'write_paths_status': 'bf90cfa6d2424aaea97cbc7342a33d90a3022ac6e104ade780cabd2d598818ad',
 'evidence_paths': '14bf48e02766e462a7140a262deed5c8895d4384867407c7b56a881c051c6dae',
 'check_contracts': 'ec38581c9638e7010124552a48c23d8af95c385223dac1eaf96d01b46036bc02'}
FITNESS_EVAL_PACKET_SHA256 = 'c7ff7540dae327264dd7d1d38ea6b9b3ce8012e719faa8665fea5646b48433e0'


def fitness_evaluation_definition_errors(task):
    """Keep source-derived offline scoring separate from quality/release claims."""
    if task.get('id') != 'KL-047':
        return []
    errors = []
    for field, expected in FITNESS_EVAL_DEFINITION_DIGESTS.items():
        actual = hashlib.sha256(json.dumps(
            task.get(field), ensure_ascii=False, sort_keys=True,
            separators=(',', ':'),
        ).encode()).hexdigest()
        if actual != expected:
            errors.append('fitness-eval-definition:KL-047:' + field)
    return errors


def fitness_evaluation_packet_errors(task, text):
    if (task.get('id') != 'KL-047'
            or task.get('packet_refinement') != 'ENFORCEABLE'):
        return []
    digest = hashlib.sha256(text.encode()).hexdigest()
    return ([] if digest == FITNESS_EVAL_PACKET_SHA256
            else ['fitness-eval-packet:KL-047'])


