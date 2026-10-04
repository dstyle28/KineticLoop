# Prospective findings resolved before final testing

The independent preliminary DB review found that actual unacquired ADMITTED S27
has NULL owner/fence0/current CREATED S29 while ReapIntent compares owner with `=`.
KL036 now explicitly permits only its specialized expected-owner null-safe basis
comparison and adds a positive exact unowned-deadline DC selector. Existing generic
fence/CAS and all request/attempt/status/deadline/time checks stay intact.

Protocol review traced RecordSnapshot/AdvanceAttempt to actual KL075, not KL028.
KL036 now reads/depends on KL075's actual PASS result/integration/owner. KL028 is
removed as an unnecessary task prerequisite; historical artifacts stay untouched.

DB/security review established that existing typed owners run through privileged
internal TEST service sessions separate from the nonwriter registered client.
Both packets explicitly disclose this existing test execution boundary and prohibit
caller SQL, target seeding, bypass, grants/roles and physical ACL/production claims.
The initial invented restricted-login requirement would have been infeasible and
has been corrected; no permission implementation is slipped into task scope.

The first C check run was deliberately interrupted for these corrections. Its raw
logs, unit failure, harness interruption and capture error are losslessly retained
under interrupted-fb0d5d9...; they are not final acceptance. The task-owned capture
runner now passes repository-relative output paths to the existing compact tool.
Substantive packet/script changes require a new C and all required checks rerun.
