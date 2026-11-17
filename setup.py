from setuptools import find_packages, setup

setup(
    name="ssl-tactical-analyzer",
    version="0.1.0",
    description="Sistema de Análise de Dados e Avaliação Tática para a Competição RoboCup SSL",
    author="Davi Giraldi Michels (UDESC CEPLAN)",
    packages=find_packages(),
    install_requires=[
        "protobuf>=3.20.0",
        "numpy>=1.20.0",
        "matplotlib>=3.1.0",
    ],
    entry_points={
        "console_scripts": [
            "ssl-analyzer=src.cli:main",
        ],
    },
    python_requires=">=3.8",
)
