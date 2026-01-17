"""
HTBase Shared Library Setup

This package contains shared code used across all HTBase microservices.
Install in editable mode: pip install -e .
"""

from setuptools import setup

setup(
    name="htbase-shared",
    version="2.0.0",
    description="Shared library for HTBase microservices",
    author="HTBase Team",
    packages=["shared"],
    package_dir={"shared": "."},
    python_requires=">=3.10",
    install_requires=[
        # Core framework
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",

        # Data validation
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",

        # Google Cloud
        "google-cloud-firestore>=2.14.0",
        "google-cloud-storage>=2.14.0",

        # Task queue
        "celery[redis]>=5.3.0",
        "redis>=5.0.0",
        "kombu>=5.3.0",

        # HTTP client
        "httpx>=0.26.0",

        # Rate limiting
        "slowapi>=0.1.9",

        # Content extraction
        "readability-lxml>=0.8.1",
        "lxml>=5.0.0",

        # Utilities
        "python-multipart>=0.0.6",
        "python-dotenv>=1.0.0",

        # AI/ML for summarization
        "chonkie==1.2.1",
        "pydantic-ai==1.0.8",
        "numpy==2.3.3",
        "huggingface_hub[inference]==0.35.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "mypy>=1.5.0",
            "ruff>=0.1.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
