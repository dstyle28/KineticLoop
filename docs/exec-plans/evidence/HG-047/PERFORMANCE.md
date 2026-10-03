# Compact validation performance correction

The initial integrated source `070f94f` read every bound plain reference through
five Git processes (two commit resolutions, tree lookup, size lookup, content
lookup), and repeatedly reloaded large historical evidence through prerequisite
validation. A bounded ten-read plain-ref probe measured 50 calls / 0.447 monotonic
seconds versus the previous existence path's 10 calls / 0.104 seconds. This was
a storage implementation regression, not justification to weaken validation.

The correction stores only successful complete-proof verdicts during one public
validation/integration/milestone operation. Nested operations share that context;
finally cleanup discards it, including after exceptions. The bounded set holds
canonical repository, exact full commit, path and tested/command/exit constraints.
It retains no raw logs. Mutable refs, working-tree reads and failures never enter
the cache. Git objects are immutable within an operation; a later operation reads
again and detects removed/corrupt objects. Owner, payload, ancestry, hash, size and
semantic checks remain mandatory before a successful entry.

The decoder also resolves a bound commit once and obtains regular-blob size from
`ls-tree -l` before fetching bytes, preserving size-before-read protection.
`benchmark.py` compares five small/large plain and compact reads against the exact
prior implementation, emitting raw call counts and monotonic elapsed durations.
The focused regressions prove cache lifetime, argument/repository/owner binding,
working-tree/HEAD freshness, missing/corrupt proof and bounded memory behavior.

The initial full harness was interrupted at 609/1265 cases and is not PASS. Its
raw log and exit 2 are retained under development-070f94f. Unit (241 cases) and
standalone authority checks completed successfully before interruption; those
prior-source results are preserved separately and are not current-source proof.
