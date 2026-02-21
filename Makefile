.PHONY: setup run dashboard demo charts clean

setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

run:
	bash src/run_self_healing.sh

demo:
	. .venv/bin/activate && python -m src.simulate_production_outputs --scenario GO --days 60 --seed 42

charts:
	. .venv/bin/activate && python -m src.executive_charts

dashboard:
	. .venv/bin/activate && streamlit run app_exec_dashboard.py --server.address 0.0.0.0 --server.port 8501

clean:
	rm -rf out/*
