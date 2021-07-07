%if 0%{?rhel} && 0%{?rhel} <= 7
%{!?py2_build: %global py2_build %{__python2} setup.py build}
%{!?py2_install: %global py2_install %{__python2} setup.py install --skip-build --root %{buildroot}}
%endif

%if (0%{?fedora} >= 21 || 0%{?rhel} >= 7)
%global with_python3 1
%endif

%define srcname slack_asterisk
%define version 0.20
%define release 1
%define sum Slack Asterisk Integration

Name:           python-%{srcname}
Version:        %{version}
Release:        %{release}%{?dist}
Summary:        %{sum}
License:        proprietary
Source0:        python-%{srcname}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python2-devel, python-setuptools, python2-mock
%{?systemd_requires}
BuildRequires: systemd
%if 0%{?with_check}
BuildRequires:  pytest
%endif # with_check
Requires:       python-setuptools, python-configobj, python-vobject, python-pyst

%{?python_provide:%python_provide python-%{srcname}}

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
%package -n python3-%{srcname}
Summary:        %{sum}
%{?python_provide:%python_provide python3-%{srcname}}
Requires:       python3-setuptools

%description -n python3-%{srcname}
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
install -p -m 644 ./slack-asterisk.service $RPM_BUILD_ROOT%{_unitdir}/slack-asterisk.service
%if 0%{?with_python3}
%py3_install
mkdir -p $RPM_BUILD_ROOT%{_unitdir}
%endif # with_python3

%if 0%{?with_check}
%check
LANG=en_US.utf8 py.test-%{python2_version} -vv tests

%if 0%{?with_python3}
LANG=en_US.utf8 py.test-%{python3_version} -vv tests
%endif # with_python3
%endif # with_check

%post
%systemd_post slack-asterisk.service

%preun
%systemd_preun slack-asterisk.service

%postun
%systemd_postun_with_restart slack-asterisk.service

%files
%dir %{python2_sitelib}/%{srcname}
%{python2_sitelib}/%{srcname}/*.*
%{python2_sitelib}/%{srcname}-%{version}-py2.*.egg-info
%{_unitdir}/slack-asterisk.service
%{_bindir}/slack-asterisk

%if 0%{?with_python3}
%files -n python3-%{srcname}
%dir %{python3_sitelib}/%{srcname}
%dir %{python3_sitelib}/%{srcname}/__pycache__
%{python3_sitelib}/%{srcname}/*.*
%{python3_sitelib}/%{srcname}/__pycache__/*.py*
%{python3_sitelib}/%{srcname}-%{version}-py3.*.egg-info
%{_unitdir}/slack-asterisk.service
%{_bindir}/slack-asterisk
%endif # with_python3

%changelog
* Thu Feb 11 2016 Dr. Torge Szczepanek <t.szczepanek@cygnusnetworks.de>
- Fix source name (t.szczepanek@cygnusnetworks.de)
