"""Делает модули проекта импортируемыми из тестов (корень в sys.path)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
