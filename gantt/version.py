# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2011 OpenStack Foundation
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import pbr.version

from nova.openstack.common.gettextutils import _

GANTT_VENDOR = "OpenStack Foundation"
GANTT_PRODUCT = "OpenStack Gantt"
GANTT_PACKAGE = None  # OS distro package version suffix

loaded = False
version_info = pbr.version.VersionInfo('gantt')
version_string = version_info.version_string


def _load_config():
    # Don't load in global context, since we can't assume
    # these modules are accessible when distutils uses
    # this module
    import ConfigParser

    from oslo.config import cfg

    from nova.openstack.common import log as logging

    global loaded, GANTT_VENDOR, GANTT_PRODUCT, GANTT_PACKAGE
    if loaded:
        return

    loaded = True

    cfgfile = cfg.CONF.find_file("release")
    if cfgfile is None:
        return

    try:
        cfg = ConfigParser.RawConfigParser()
        cfg.read(cfgfile)

        GANTT_VENDOR = cfg.get("Gantt", "vendor")
        if cfg.has_option("Gantt", "vendor"):
            GANTT_VENDOR = cfg.get("Gantt", "vendor")

        GANTT_PRODUCT = cfg.get("Gantt", "product")
        if cfg.has_option("Gantt", "product"):
            GANTT_PRODUCT = cfg.get("Gantt", "product")

        GANTT_PACKAGE = cfg.get("Gantt", "package")
        if cfg.has_option("Gantt", "package"):
            GANTT_PACKAGE = cfg.get("Gantt", "package")
    except Exception as ex:
        LOG = logging.getLogger(__name__)
        LOG.error(_("Failed to load %(cfgfile)s: %(ex)s"),
                  {'cfgfile': cfgfile, 'ex': ex})


def vendor_string():
    _load_config()

    return GANTT_VENDOR


def product_string():
    _load_config()

    return GANTT_PRODUCT


def package_string():
    _load_config()

    return GANTT_PACKAGE


def version_string_with_package():
    if package_string() is None:
        return version_info.version_string()
    else:
        return "%s-%s" % (version_info.version_string(), package_string())
