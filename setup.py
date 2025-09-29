from setuptools import setup, find_packages
from pathlib import Path
long_description = (Path(__file__).parent / "README.md").read_text()


setup(
    name='berlin-appointment-finder',
    version='2.0.0',
    description='Finds appointments at the Berlin Bürgeramt, broadcasts them via websockets',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://allaboutberlin.com/tools/appointment-finder',
    project_urls={
        'Documentation': 'https://github.com/All-About-Berlin/burgeramt-appointments',
        'Funding': 'https://allaboutberlin.com/donate',
        'Source Code': 'https://github.com/All-About-Berlin/burgeramt-appointments',
        'Issues': 'https://github.com/All-About-Berlin/burgeramt-appointments/issues'
    },
    author='Nicolas Bouliane',
    author_email='contact@nicolasbouliane.com',
    license='MIT',
    packages=find_packages(),
    scripts=['bin/appointments'],
    python_requires='>=3.10',
    install_requires=[
        'chime==0.7.0',
        'playwright==1.55.0',
        'pytz',
        'websockets==14.2',
    ],
    zip_safe=False,
)
