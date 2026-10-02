# Selected versus development evidence

The governance result's tested_commit selects the final acceptance round. Its
implementation, tests and check scripts remain unchanged during that round.
The e748b37 round is superseded by independent review findings at 351f0ed:
full selector contribution and strict integer exit-code checks required repair.
Those CHANGES_REQUIRED reviews and their reproductions are retained in the own
review tree; fresh independent reviews must bind the repaired result SHA.

Reports launched at26a9a39,0874228,dccac06,53d94e4 and4a9b4c6 are retained
development output. Each report identifies its launch revision; further refinements
were committed while those rounds were running. They are superseded and must not
be used as clean final SHA-bound acceptance authority, even when the process result
says PASS. The governance record references only its selected fresh round.
The initial uncommitted42PASS focused run is likewise not selected evidence.
No historical/development fixture logs are reused as new PASS.

The 4302c06 round passed at its original protected base. It is superseded for
final acceptance because master advanced to fa729ca with the KL029 merge while
reviews of 080f25c were starting. Those reviews were interrupted; partial r2 raw
files carry no final PASS authority. Fresh checks and four fresh reviews must
bind the refreshed protected base and committed result.

The 0af3580 checks passed, but independent review at19dc5a4 found valid real
pytest parameter IDs falsely rejected by JUnit matching and collection summary
classification. That round is superseded; the fixes and genuine pytest-format
tests require a new committed check round and fresh independent reviews.
