from setuptools import setup, find_packages
from pathlib import Path
long_description = (Path(__file__).parent / "README.md").read_text()


setup(
    name='berlin-appointment-finder',
    version='1.0.2',
    description='Finds appointments at the Berlin Bürgeramt, broadcasts them via websockets',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/nicbou/burgeramt-appointments-websockets',
    author='Nicolas Bouliane',
    author_email='contact@nicolasbouliane.com',
    license='MIT',
    packages=find_packages(),
    scripts=['bin/appointments'],
    python_requires='>=3.10',
    install_requires=[
        'aiohttp==3.8.4',
        'beautifulsoup4==4.10.0',
        'chime==0.7.0',
        'pytz',
        'websockets==10.1',
        'lxml==4.7.1',
    ],
    zip_safe=False,
)
