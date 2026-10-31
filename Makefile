PYTHON ?= python3

.PHONY: all profiles run analyze plots clean

all: profiles run analyze plots

profiles:
	$(PYTHON) scripts/generate_profiles.py

run:
	$(PYTHON) scripts/run_cases.py --all-candidates

analyze:
	$(PYTHON) scripts/analyze.py

plots:
	$(PYTHON) scripts/plot_results.py

clean:
	rm -f outputs/*.csv outputs/logs/*.log gridlabd.xml
	rm -rf outputs/analysis
	rm -f figures/*.png
	rm -rf glm/cases/generated
