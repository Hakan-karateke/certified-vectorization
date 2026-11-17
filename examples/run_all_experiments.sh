#!/usr/bin/env bash
# Makaledeki bütün ikon deneylerini sırayla koşar (yerel çözünürlük, sürüm 3.0).
# Depo kökünden çalıştırın:  bash examples/run_all_experiments.sh [işçi sayısı]
# Her aşama kendi günlüğünü .tmp/exp30/ altına yazar; bir aşama hata verirse
# zincir sonraki aşamayla devam eder. Toplam süre 12 işçiyle yaklaşık 14 saattir.
set -u
PY=.venv/Scripts/python.exe
W=${1:-12}
D=examples/icon_dataset
M=$D/manifest.json
S=$D/sample200.json
POTRACE=.tmp/potrace/potrace-1.16.win64/potrace.exe
LOG=.tmp/exp30
mkdir -p $LOG

stage() { echo "$(date '+%F %T') $1" | tee -a $LOG/progress.log; }

stage "1 optimality_gap"
$PY examples/optimality_gap.py $M $D/optimality_gap_3.0 --workers $W > $LOG/gap.log 2>&1

stage "2 contact icon list"
$PY -c "
import json
r = json.load(open('$D/optimality_gap_3.0/results.json', encoding='utf-8'))['results']
ids = sorted({x['id'] for x in r if x['midpoint'].get('contact_points', 0) > 0})
json.dump({'ids': ids}, open('$D/contact_icons_3.0.json', 'w'), indent=1)
print(len(ids), 'icons with contacts')
" > $LOG/contacts.log 2>&1

stage "3 pipeline sweep"
IDS=$($PY -c "import json;print(' '.join(json.load(open('$S',encoding='utf-8'))['ids']))")
$PY -m sekilden_denkleme.stress $M output/icons-3.0 --workers 8 --timeout 2400 --ids $IDS > $LOG/sweep.log 2>&1
$PY examples/summarize_sweep.py output/icons-3.0/cases $D/pipeline_sweep_3.0 > $LOG/sweep_summary.log 2>&1

stage "4 line_arc_optimum"
$PY examples/line_arc_optimum.py $M $D/line_arc_optimum_3.0 --ids-file $S --workers $W > $LOG/arcs.log 2>&1

stage "5 potrace comparison"
$PY examples/compare_potrace.py $M $POTRACE $D/potrace_comparison_3.0 --workers $W > $LOG/potrace.log 2>&1

stage "6 potrace certification"
$PY examples/certify_potrace.py $M $POTRACE $D/potrace_certified_3.0 --workers $W > $LOG/potrace_cert.log 2>&1

stage "7 line-arc sensitivity and smoothing"
$PY examples/line_arc_sensitivity.py arcs $M $D/line_arc_sensitivity_3.0 --ids-file $S --limit 80 --workers $W > $LOG/sens_arcs.log 2>&1

stage "8 clearance sensitivity"
$PY examples/line_arc_sensitivity.py clearance $M $D/clearance_contacts_3.0 --ids-file $D/contact_icons_3.0.json --workers $W > $LOG/clear_contacts.log 2>&1
$PY examples/line_arc_sensitivity.py clearance $M $D/clearance_sample_3.0 --ids-file $S --workers $W > $LOG/clear_sample.log 2>&1

stage "9 scan degradation"
$PY examples/scan_degradation.py scan $M $D/scan_degradation_3.0 --ids-file $S --limit 100 --workers $W > $LOG/scan.log 2>&1

stage "10 resampling topology"
$PY examples/scan_degradation.py resample $M $D/resampling_topology_3.0 --workers $W > $LOG/resample.log 2>&1

stage "11 compiled kernel"
$PY examples/compiled_kernel/compare.py examples/compiled_kernel/results_3.0 > $LOG/kernel.log 2>&1

stage "done"
