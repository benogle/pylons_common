try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

setup(
    name='pylons_common',
    version='0.0.1',
    description='Common pylons utilities',
    author='Ben Ogle',
    author_email='human@benogle.com',
    url='http://github.com/benogle/pylons_common',
    install_requires=[
        "Pylons>=1.0",
        "SQLAlchemy>=0.5",
        "pytz==2010e",
    ],
    packages=find_packages(exclude=['ez_setup']),
    include_package_data=True,
    test_suite='nose.collector',
    
    zip_safe=False,
    
    license = "MIT License",
    
    classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Topic :: Internet',
    ]
    
)
