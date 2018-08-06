%if 0%{?rhel} && 0%{?rhel} <= 7
%{!?py2_build: %global py2_build %{__python2} setup.py build}
%{!?py2_install: %global py2_install %{__python2} setup.py install --skip-build --root %{buildroot}}
%endif

%if (0%{?fedora} >= 21 || 0%{?rhel} >= 8)
%global with_python3 1
%endif

%define srcname ivr
%define version 2.00
%define release 1
%define sum Cygnus Networks GmbH %{srcname} package

Name:           python-%{srcname}
Version:        %{version}
Release:        %{release}%{?dist}
Summary:        %{sum}
License:        proprietary
Source0:        python-%{srcname}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python2-devel, python-setuptools, python2-mock, python-pyrad, python-cygnustoolkit, PyYAML
%{?systemd_requires}
BuildRequires: systemd
%if 0%{?with_check}
BuildRequires:  pytest
%endif # with_check
Requires:       python-setuptools, python-configobj, python-vobject, python-cygnustoolkit, python-ipaddress, python-jinja2, python2-future, python2-jmespath, python2-futures, PyYAML, python-requests, python-pyst, python-requests, python-boto3, python2-botocore

%{?python_provide:%python_provide python-%{project}}

%if 0%{?with_python3}
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
%if 0%{?with_check}
BuildRequires:  python3-pytest
%endif # with_check
%endif # with_python3

%description
%{sum}

%if 0%{?with_python3}
%package -n python3-%{project}
Summary:        %{sum}
%{?python_provide:%python_provide python3-%{project}}
Requires:       python3-setuptools

%description -n python3-%{project}
%{sum}
%endif # with_python3

%prep
%setup -q -n python-%{srcname}-%{version}

%build
%py2_build

%if 0%{?with_python3}
%py3_build
%endif # with_python3


%install
%py2_install
mkdir -p $RPM_BUILD_ROOT%{_unitdir}
mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}/ivr
mkdir -p $RPM_BUILD_ROOT%{_datadir}/ivr/ivrcontrol
install -p -m 644 ./ivr@.service $RPM_BUILD_ROOT%{_unitdir}/ivr@.service
install -p -m 644 ./static/dictionary.rfc2865 $RPM_BUILD_ROOT%{_sysconfdir}/ivr/dictionary.rfc2865
install -p -d -m 755 ./ivrcontrol $RPM_BUILD_ROOT%{_datadir}/ivr/ivrcontrol
cp -a ./ivrcontrol/* $RPM_BUILD_ROOT%{_datadir}/ivr/ivrcontrol/
%if 0%{?with_python3}
%py3_install
mkdir -p $RPM_BUILD_ROOT%{_unitdir}
mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}/ivr
mkdir -p $RPM_BUILD_ROOT%{_datadir}/ivr/ivrcontrol
install -p -m 644 ./ivr@.service $RPM_BUILD_ROOT%{_unitdir}/ivr@.service
install -p -m 644 ./static/dictionary.rfc2865 $RPM_BUILD_ROOT%{_sysconfdir}/ivr/dictionary.rfc2865
install -p -d -m 755 ./ivrcontrol $RPM_BUILD_ROOT%{_datadir}/ivr/ivrcontrol
cp -a ./ivrcontrol/* $RPM_BUILD_ROOT%{_datadir}/ivr/ivrcontrol/
%endif # with_python3

%if 0%{?with_check}
%check
LANG=en_US.utf8 py.test-%{python2_version} -vv tests

%if 0%{?with_python3}
LANG=en_US.utf8 py.test-%{python3_version} -vv tests
%endif # with_python3
%endif # with_check

%post
%systemd_post ivr@.service

%preun
%systemd_preun ivr@.service

%postun
%systemd_postun_with_restart ivr@.service

%files
%dir %{_datadir}/ivr/ivrcontrol
%dir %{python2_sitelib}/%{srcname}
%dir %{python2_sitelib}/%{srcname}/scripts
%dir %{python2_sitelib}/%{srcname}/modules
%dir %{python2_sitelib}/%{srcname}/modules/say_provider
%{_sysconfdir}/ivr/dictionary.rfc2865
%{_datadir}/ivr/ivrcontrol/*
%{python2_sitelib}/%{srcname}/*.*
%{python2_sitelib}/%{srcname}/scripts/*.*
%{python2_sitelib}/%{srcname}/modules/*.*
%{python2_sitelib}/%{srcname}/modules/say_provider/*.*
%{python2_sitelib}/%{srcname}-%{version}-py2.*.egg-info
%{_unitdir}/ivr@.service
%{_bindir}/ivr-fastagi-daemon
%{_bindir}/ivr-public-holiday

%if 0%{?with_python3}
%files -n python3-%{project}
%dir %{_sysconfdir}/ivr
%dir %{_datadir}/ivr/ivrcontrol
%dir %{python3_sitelib}/%{srcname}
%dir %{python3_sitelib}/%{srcname}/scripts
%dir %{python3_sitelib}/%{srcname}/modules
%dir %{python3_sitelib}/%{srcname}/modules/say_provider
%dir %{python3_sitelib}/%{srcname}/__pycache__
%{_sysconfdir}/ivr/dictionary.rfc2865
%{_datadir}/ivr/ivrcontrol/*
%{python3_sitelib}/%{srcname}/*.*
%{python3_sitelib}/%{srcname}/scripts/*.*
%{python3_sitelib}/%{srcname}/modules/*.*
%{python3_sitelib}/%{srcname}/modules/say_provider/*.*
%{python3_sitelib}/%{srcname}/__pycache__/*.py*
%{python3_sitelib}/%{srcname}-%{version}-py3.*.egg-info
%{_unitdir}/ivr@.service
%{_bindir}/ivr-fastagi-daemon
%{_bindir}/ivr-public-holiday
%endif # with_python3

%changelog
* Thu Feb 11 2016 Dr. Torge Szczepanek <t.szczepanek@cygnusnetworks.de>
- Fix source name (t.szczepanek@cygnusnetworks.de)
