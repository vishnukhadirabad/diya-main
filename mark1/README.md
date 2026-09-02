# mark1 — STUB work directory

**These are not the real CV scripts.** They are placeholders created so that
`DiyaMeditation/scripts/run1.sh` can be run end to end on this machine.

`run1.sh` requires `$HOME/Desktop/mark1` to exist and to contain
`HOME1.py`, `SHOOT1.py`, `CHEST1.py`, `EYE1.py`. The real versions drive the
cameras and the CV steps; they were not present anywhere on this machine and
are not in the Diya repo.

Each stub here prints one line and exits 0. That exercises the pipeline's
sequencing, retry logic, and the final `meditation-app` launch — it does
**not** test any actual detection, capture, or measurement.

Replace each file with the genuine script when it is available. Nothing else
needs to change.
