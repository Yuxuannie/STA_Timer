# Reference tools

Contract: `docs/contracts/reference.md`. Results go to `ref/results/`
(git-ignored).

```
ref/opensta/run.sh --probe                 # 0 if OpenSTA can read data/toy2.lib
ref/run_all.sh                             # eight P2 designs + s1423
ref/run_all.sh s27                         # one design
STA_BIN=/path/to/sta ref/run_all.sh        # another binary
```

## OpenSTA install (P5, R39)

- Route: 2 (source build). Route 1 was not possible: no Docker on this Mac.
- Version: **OpenSTA 3.1.0**, commit
  `444cfc701ce34e0cf3dc73bbad3a9c2b56ad8c08` (2026-11-05) of
  `https://github.com/The-OpenROAD-Project/OpenSTA` (shallow clone of the
  default branch).
- Binary: `~/tools/opensta/build/sta` (the default of `run.sh`; `$STA_BIN`
  overrides it).
- Machine: macOS 15.7.4, x86_64 (Intel), Apple clang 17.0.0.
- Time: box opened 21:52:37, `sta` built 22:15:15, first full run 22:17
  (25 minutes of the 90-minute box).

Steps that worked:

1. `brew install cmake tcl-tk swig bison flex eigen zlib` failed: Homebrew 6
   treats this Intel Mac as Tier 3 and has no bottles for `cmake`, `tcl-tk`,
   `swig`, `zlib`.
2. Bottles: `brew install bison flex eigen` (bison 3.8.2, flex 2.6.4,
   eigen 5.0.1; bison and flex are keg-only under `/usr/local/opt`).
3. From source: `brew install --build-from-source cmake` (4.4.5),
   `... swig` (4.5.1), `... tcl-tk@8` (8.6, the version in OpenSTA's
   `Brewfile`; its post-install step warned, the library and headers are
   installed). zlib: the macOS SDK's (1.2.12), found by CMake.
4. CUDD 3.0.0: `git clone https://github.com/cuddorg/cudd.git; git checkout
   3.0.0; ./configure --prefix=$HOME/tools/cudd; make; make install`.
5. OpenSTA (`~/tools/build_opensta.sh`):
   ```
   cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF -DUSE_TCL_READLINE=OFF \
     -DCUDD_DIR=$HOME/tools/cudd \
     -DTCL_LIBRARY=/usr/local/opt/tcl-tk@8/lib/libtcl8.6.dylib \
     -DTCL_HEADER=/usr/local/opt/tcl-tk@8/include/tcl-tk/tcl.h \
     -DCMAKE_PREFIX_PATH=/usr/local/opt/eigen \
     -DBISON_EXECUTABLE=/usr/local/opt/bison/bin/bison \
     -DFLEX_EXECUTABLE=/usr/local/opt/flex/bin/flex \
     -DFLEX_INCLUDE_DIR=/usr/local/opt/flex/include \
     -DSWIG_EXECUTABLE=/usr/local/bin/swig
   make -j10 sta
   ```
   (`BUILD_TESTS=OFF` because GoogleTest is not installed.)

## Settings in `run.tcl`

- `read_sdc` reads the toy's SDC files unchanged: OpenSTA 3.1.0 accepted all
  nine without an error or a warning, so no SDC construct needed an
  adaptation.
- Ideal clocks, no parasitics, no wire load (`toy2.lib` has none),
  `set_delay_calculator lumped_cap`, `set_cmd_units -time ns -capacitance pF`
  (the library's own units; `units.txt` confirms 1ns / 1pF).
- Values through `get_property` (pin `arrival_*`, `slack_*`, `slew_*`, 6
  digits); paths through `find_timing_paths` and `get_property $end points`;
  `report_checks -format full_clock_expanded` text for people.
  `report_checks -format json` exists in this version but has no rise/fall
  per point, so it is not used.

## Known gaps and differences seen in the first runs

For R40 (the lead classifies; nothing here is a verdict):

- CK pins under an ideal clock: `get_property` gives the graph slew (0 when
  the clock port has no input transition) where the toy has
  `set_clock_transition`; the CK pin arrival does not include the ideal
  latency (it does reach Q); CK pins and the clock port have a fall arrival
  at half the period and values where the toy has `NA`.
- Clock latency is added to input-delay arrivals (s27: +0.2).
- A PI with only `set_input_delay -max` gets that value for min too (s27
  `G3`), where the toy uses 0.
- Clock latency and uncertainty enter output-port required times (ff2_swap: +0.3 latency; ff2_unc: setup -0.5, hold +0.3), where the toy uses neither.
- The launching CK pin's edge in `paths.txt` is written as rise (not exposed
  in Tcl; true for `toy2.lib`).
