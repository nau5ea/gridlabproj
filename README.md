# EE 5/430 Term Project: Load Modeling Using GridLAB-D

Skeleton implementation of the three-house residential load study described in
`GridLAB-D Project.pdf`.

The model represents three houses on the secondary of one shared single-phase
center-tapped transformer.  Each house has:

- one explicit `triplex_load` for household demand excluding water heating,
  driven by a player;
- one explicit `waterheater` for water-heating demand, driven by a gpm water-draw
  player;
- one `triplex_meter` upstream of both loads.

The project also includes the four required ZIP cases, a transformer-candidate
runner, measurement extraction, validation metrics, and plotting scripts.

> **Data status:** the course-provided demand and water-draw datasets were not
> present in this directory.  The repository therefore ships deterministic
> synthetic placeholder profiles (seed 530) so the skeleton is runnable.  Replace
> `data/input/*.csv` with the official files and rerun
> `scripts/generate_profiles.py` before using any result in the report.

## GridLAB-D version

This skeleton was executed with:

```text
GridLAB-D 5.3.0-20236 (e1841e1e:master) 64-bit LINUX RELEASE
```

The runner uses `gridlabd` from `PATH`, the `GRIDLABD` environment variable, or
the sibling build tree `../gridlab-d/cmake-build/bin/gridlabd`.

## Quick start

From the repository root, either run the four steps below or use
`make all`.

```bash
# 1. Create the placeholder input CSVs and GridLAB-D player files.
python3 scripts/generate_profiles.py

# 2. Run the four ZIP cases for all transformer candidates.
python3 scripts/run_cases.py --all-candidates

# 3. Compute Task 2/3 metrics and the candidate comparison.
python3 scripts/analyze.py

# 4. Create the figures.
python3 scripts/plot_results.py

# 5. Optional: regenerate the one-line diagram.
dot -Tpng docs/one_line_diagram.dot -o docs/one_line_diagram.png
```

A single case can be run directly:

```bash
gridlabd -W . glm/cases/constant_power.glm
```

Run GridLAB-D from the repository root.  The model references player files and
writes recorder output with paths relative to the working directory.
`scripts/run_cases.py` writes the generated wrapper GLMs for each
(case, rating) pair to `glm/cases/generated/` and records their commands in
`outputs/runs.csv`.

The house objects emit a `no climate data found, using static data` warning
because HVAC is disabled and no weather file is supplied.  That warning does not
affect the electrical results.

## Repository layout

```text
glm/
  model.glm                 three-house model, shared transformer, recorders
  cases/
    constant_power.glm      ZIP case 1
    constant_current.glm    ZIP case 2
    constant_impedance.glm  ZIP case 3
    mixed.glm               ZIP case 4 (30% P, 30% I, 40% Z)

data/
  input/                    source CSVs (kW and gpm)
  players/                  GridLAB-D player files (VA and gpm)
  profiles_metadata.json    seed and summary of the placeholder profiles

scripts/
  generate_profiles.py      CSV -> player conversion and placeholder generation
  run_cases.py              ZIP/candidate runner and outputs/runs.csv manifest
  gridlab_io.py             recorder readers and complex-value parser
  analyze.py                validation, ZIP, and candidate metrics
  plot_results.py           Task 2/3 figures

docs/
  one_line_diagram.dot/.png/.svg
  input_assignment_table.md

outputs/
  *.csv                     recorder output (one set per case and rating)
  runs.csv                  run manifest
  analysis/                 metrics tables, JSON summaries, recommendation
  logs/                     GridLAB-D console logs

figures/                    generated Task 2/3 plots
```

## Model details

### Network

- 7.2 kV primary swing node (`source_bus`, phase C-N).
- Shared `transformer_configuration` with
  `connect_type SINGLE_PHASE_CENTER_TAPPED`, 7200 V primary, 120 V secondary
  leg-to-neutral (240 V leg-to-leg).
- Transformer candidates: 10, 15, 25, and 37.5 kVA.  The default case files use
  25 kVA.
- 240/120 V triplex secondary bus and 50/75/100 ft triplex service drops.
- One `triplex_meter` per service.  The household `triplex_load` and the
  water-heater `house` are both downstream of that meter.

### Load objects

- `house_load_1/2/3` are `triplex_load` objects.  Their `base_power_1` and
  `base_power_2` are driven by `data/players/houseN_load.player`.
- The player values are apparent power in VA:
  `base_power_leg = (P_kW * 1000 / 2) / 0.95`.
- The household demand is split equally between the two 120 V legs.  Phase
  redistribution is not performed.
- A common 0.95 lagging power factor is used for all ZIP components.
- `house_1/2/3` are used only as thermal hosts for the water heaters.  HVAC is
  disabled with `heating_system_type NONE`, `cooling_system_type NONE`,
  `auxiliary_system_type NONE`, `system_mode OFF`, and
  `thermostat_control NONE`.  `module residential { implicit_enduses NONE; }`
  disables implicit appliance demand.
- `wh_1/2/3` are explicit `waterheater` objects with the required settings:
  indoor, 120 degF setpoint, 50 gal tank, 2 degF dead band, 4.5 kW element,
  60 degF inlet, and tank UA 3.3 Btu/(h*degF).
- The initial tank state is 120 degF and a full tank.  This is documented in the
  GLM and in `docs/input_assignment_table.md`.

### Measurement boundaries

- Transformer loading: `xfmr.power_in` (primary-side input apparent power).
- Transformer losses: `xfmr.power_in - xfmr.power_out`.
- Service combined demand: `service_meter_N.measured_power`, downstream of the
  service drop and upstream of both the household load and water heater.
- Source-to-service balance: transformer primary input real power minus the sum
  of the three service-meter real powers.  The difference contains transformer
  and service-drop losses inside that boundary.
- Service voltage: `measured_voltage_1` and `measured_voltage_2`, interpreted as
  line-to-neutral magnitudes on a 120 V base.  The reported line-to-line value
  is the sum of the two leg-to-neutral magnitudes, with a 240 V base.

### ZIP cases

All four cases use the same nominal household profiles, water draws,
water-heater settings, initial conditions, and network configuration:

| Case | P | I | Z |
|---|---:|---:|---:|
| `constant_power` | 1.00 | 0.00 | 0.00 |
| `constant_current` | 0.00 | 1.00 | 0.00 |
| `constant_impedance` | 0.00 | 0.00 | 1.00 |
| `mixed` | 0.30 | 0.30 | 0.40 |

Only the three `triplex_load` objects receive the ZIP fractions.  The explicit
water-heater models are unchanged and may respond electrically to the changed
voltage.

## Results produced by the skeleton

`scripts/analyze.py` writes:

- `outputs/analysis/case_metrics.csv`
- `outputs/analysis/candidate_comparison.csv`
- `outputs/analysis/zip_comparison.csv`
- `outputs/analysis/recommendation.json`
- `outputs/analysis/summary_<case>_xfmr<rating>kva.json`

`scripts/plot_results.py` writes:

- `figures/demand_components_<case>.png`
- `figures/source_service_balance_<case>.png`
- `figures/water_heaters_<case>.png`
- `figures/zip_comparison.png`
- `figures/candidate_loading.png`
- `figures/candidate_voltage.png`

The current placeholder run selects **25 kVA**: the 15 kVA candidate exceeds
100% nameplate loading in every ZIP case, while 25 kVA remains below 100% and
keeps service voltages within 0.95-1.05 p.u.  These numbers are placeholder
results, not the official project results.

ZIP comparison at 25 kVA (placeholder data):

| Case | Peak transformer input (kVA) | Peak loading (%) | Min leg voltage (p.u.) | Transformer energy (kWh/day) | Service energy (kWh/day) | Loss energy (kWh/day) |
|---|---:|---:|---:|---:|---:|---:|
| constant power | 20.922 | 83.69 | 0.98242 | 101.845 | 101.433 | 0.4113 |
| constant current | 20.810 | 83.24 | 0.98277 | 101.253 | 100.848 | 0.4059 |
| constant impedance | 20.666 | 82.66 | 0.98277 | 100.677 | 100.276 | 0.4004 |
| mixed | 20.785 | 83.14 | 0.98267 | 101.197 | 100.791 | 0.4054 |

Candidate screening (worst case across the four ZIP cases):

| Rating (kVA) | Worst peak loading (%) | Worst min voltage (p.u.) | Worst overload duration (min) | Pass all cases? |
|---:|---:|---:|---:|---|
| 10 | 207.75 | 0.95462 | 138 | no |
| 15 | 139.06 | 0.97075 | 49 | no |
| 25 | 83.69 | 0.98242 | 0 | yes |
| 37.5 | 55.87 | 0.98784 | 0 | yes |

Overload duration is counted from the one-minute recorder samples.  Each sample
is treated as representing the one-minute interval beginning at its timestamp;
the 1440 samples cover the simulated day.  Nameplate exceedance is a loading
screen, not a thermal-damage calculation.

`outputs/runs.csv` records the exit code and log path for every run.  A
non-convergent run appears there with a nonzero exit code and is excluded from
the numerical comparison, rather than being treated as a voltage or loading
violation.

### Numerical checks

- Transformer primary input real power minus the sum of the three service-meter
  real powers is the loss inside the transformer + service-drop boundary.  In
  the placeholder constant-power case, the maximum difference is about 0.21 kW
  and the daily energy difference is 0.411 kWh out of 101.845 kWh.
- At each service, the service-meter real power should equal the household
  `triplex_load` plus the water-heater electrical demand.  The maximum absolute
  one-minute discrepancy in the placeholder runs is about 0.15 kW, and the daily
  energy discrepancy is about -0.015 kWh per house.  These small differences are
  consistent with voltage-dependent load evaluation and recorder resolution, not
  with double-counted demand.

## Replacing the placeholder data

1. Put the official household demand CSVs in `data/input/` using the columns
   `timestamp,demand_kw`.
2. Put the official water-draw CSVs in `data/input/` using the columns
   `timestamp,water_gpm`.
3. Keep the filenames `house1_demand.csv`, `house1_water.csv`, etc., or update
   `scripts/generate_profiles.py`.
4. Rerun `python3 scripts/generate_profiles.py`.
5. If the assigned day changes, update `START` in `scripts/generate_profiles.py`
   and the `clock` block in `glm/model.glm` together.
6. Rerun the runner, analysis, and plots.

Missing or invalid input values are not silently converted to zero by the model.
The placeholder generator produces complete one-minute records; a real-data
preparation step should validate gaps, duplicates, units, and timezone before
writing players.

## Assumptions and limitations

- The provided course datasets and starter model were not available in this
  directory; the placeholder profiles are synthetic and deterministic.
- The 0.95 lagging power factor is a study assumption, not an inferred dataset
  property.
- The household demand is balanced across the two 120 V legs.
- The water heater uses GridLAB-D's one-node model.  The initial tank state is
  documented as 120 degF and full.
- The transformer and service-drop impedances are skeleton values; replace them
  with the starter model values when available.
- The study covers one simulated day.  It does not establish year-round
  transformer adequacy.
- The repository does not include the IEEE-format paper or undergraduate report;
  it provides the reproducible model, data, analysis, and figures those
  deliverables require.

## Collaboration and external assistance

This skeleton was developed with assistance from **DeepSeek V4.1 Flash Free**
(OpenCode coding agent).  The AI helped structure the GridLAB-D model, write the
profile generator, runner, analysis, and plotting scripts, and document the
assumptions.  All numerical results should be independently checked by the
student before submission, and the course collaboration policy should be
followed when acknowledging assistance.
