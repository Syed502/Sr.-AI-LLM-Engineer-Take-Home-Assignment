.PHONY: help install test evaluate run deploy clean web

help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make test       - Run all tests"
	@echo "  make evaluate   - Run cart normalization evaluation"
	@echo "  make run        - Run the voice client"
	@echo "  make web        - Run the web application"
	@echo "  make deploy     - Deploy to Heroku"
	@echo "  make clean      - Clean temporary files"

install:
	pip install -r requirements.txt

test:
	python evaluate.py --verbose

evaluate:
	python evaluate.py

evaluate-small:
	python evaluate.py --menu small

evaluate-large:
	python evaluate.py --menu large

run:
	python main.py

run-small-menu:
	python main.py --system-prompt "$(shell cat prompts/small_menu_prompt.txt)"

run-large-menu:
	python main.py --system-prompt "$(shell cat prompts/large_menu_prompt.txt)"

web:
	python web_app.py

deploy:
	git push heroku main

clean:
	rm -f evaluation_report_*.json
	rm -rf __pycache__ *.pyc
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete



