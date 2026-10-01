
M3_NEXT_WAVE_IDS = frozenset({'KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077'})
M3_NEXT_WAVE_DEFINITION_HASHES = None  # ratified from drafts
M3_NEXT_WAVE_PACKET_HASHES = None  # ratified from drafts


def m3_next_wave_definition_errors(task):
    name = task.get('id')
    if name not in M3_NEXT_WAVE_IDS or (
            task.get('packet_refinement') != 'ENFORCEABLE'
            and 'check_contracts' not in task):
        return []
    actual = hashlib.sha256(json.dumps(
        task, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'),
    ).encode()).hexdigest()
    return ([] if actual == M3_NEXT_WAVE_DEFINITION_HASHES[name]
            else ['m3-next-wave-definition:' + name])


def m3_next_wave_packet_errors(task, text):
    name = task.get('id')
    if name not in M3_NEXT_WAVE_IDS or (
            task.get('packet_refinement') != 'ENFORCEABLE'
            and 'check_contracts' not in task):
        return []
    actual = hashlib.sha256(text.encode()).hexdigest()
    return ([] if actual == M3_NEXT_WAVE_PACKET_HASHES[name]
            else ['m3-next-wave-packet:' + name])
