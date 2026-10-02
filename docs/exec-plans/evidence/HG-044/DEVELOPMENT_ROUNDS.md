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
