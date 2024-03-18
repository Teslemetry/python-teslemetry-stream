import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="teslemetry_stream",
    version="0.2.0",
    author="Brett Adams",
    author_email="hello@teslemetry.com",
    description="Teslemetry Streaming API library for Python",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Teslemetry/teslemetry_stream",
    packages=setuptools.find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=["aiohttp", "asyncio"],
)
