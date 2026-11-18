# State Supreme Court Election Archive (raw)

Herbert M. Kritzer's State Supreme Court Election Archive (University of
Minnesota Law School; dated April 5, 2015, updated February 9, 2024), as
distributed. The files are unmodified. Kritzer compressed every spreadsheet
with 7-Zip to get past Dataverse's ingest step. These are the inputs to
`../scdb-expert/scripts/build_state_elections.py`.

| file | contents |
|---|---|
| `Documentation-State_Supreme_Court_Election_Archive.docx` | codebook |
| `ElectionDataset.7z` | `ElectionDataset.xlsx`, saved 2024-03-07: the corrected version, used by the build |
| `RetentionDataset.7z` | `RetentionDataset.xlsx` |
| `AllFiles.7z` | the 38 state workbooks (county returns, justice lists, sources), plus `SeatsDataset.xlsx`, `RetentionDataset.xlsx` and an earlier `ElectionDataset.xlsx` (2024-02-09, with 39 duplicated electids) |

The codebook calls the complete archive `All_SSC_Data.7z`; it arrived here as
`AllFiles.7z`. The `MergeStates.do` file that the codebook mentions (it builds
Seats from the state workbooks) is not included.

You don't need 7-Zip:

```bash
python ../scdb-expert/scripts/un7z.py AllFiles.7z            # list
python ../scdb-expert/scripts/un7z.py AllFiles.7z /tmp/ssc   # extract
```

Rebuild the cleaned tables (the output is identical to what is committed in
`scdb-expert/data/state/`):

```bash
python scdb-expert/scripts/build_state_elections.py --raw state-elections-raw \
       --out scdb-expert/data/state
```

| file | SHA-256 |
|---|---|
| `AllFiles.7z` | `e6c79274012e657cce4275369aa62303d780923b3109f6bb2580f498efd24521` |
| `ElectionDataset.7z` | `36570845fcfb11214e4483b4fd4fd95bea9ec48c9be6d98f85d2a16c4e384a8a` |
| `RetentionDataset.7z` | `ea01b68f81443b727de1132d5511fc89bc1abbbdabe8be3fdef84142f594fe90` |
| `Documentation-…Archive.docx` | `d51ee02a040f0c517ee89dcecd45d6c2dc0737f63d209c6aacb79813e18f3813` |
