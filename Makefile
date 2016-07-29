example: .PHONY
	PYTHONPATH=. example/kernel.py

test: .PHONY
	PYTHONPATH=. tests/example.py

pylint: .PHONY
	pylint schedsi example/kernel.py tests/example.py

.PHONY:
