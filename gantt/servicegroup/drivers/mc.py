# Service heartbeat driver using Memcached
# Copyright (c) 2013 Akira Yoshiyama <akirayoshiyama at gmail dot com>
#
# This is derived from nova/servicegroup/drivers/db.py.
# Copyright 2012 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo.config import cfg

from nova import conductor
from nova import context
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging
from nova.openstack.common import memorycache
from nova.openstack.common import timeutils
from nova.servicegroup import api


CONF = cfg.CONF
CONF.import_opt('service_down_time', 'nova.service')
CONF.import_opt('memcached_servers', 'nova.openstack.common.memorycache')


LOG = logging.getLogger(__name__)


class MemcachedDriver(api.ServiceGroupDriver):

    def __init__(self, *args, **kwargs):
        test = kwargs.get('test')
        if not CONF.memcached_servers and not test:
            raise RuntimeError(_('memcached_servers not defined'))
        self.mc = memorycache.get_client()
        self.db_allowed = kwargs.get('db_allowed', True)
        self.conductor_api = conductor.API(use_local=self.db_allowed)

    def join(self, member_id, group_id, service=None):
        """Join the given service with its group."""

        msg = _('Memcached_Driver: join new ServiceGroup member '
                '%(member_id)s to the %(group_id)s group, '
                'service = %(service)s')
        LOG.debug(msg, {'member_id': member_id, 'group_id': group_id,
                        'service': service})
        if service is None:
            raise RuntimeError(_('service is a mandatory argument for '
                                 'Memcached based ServiceGroup driver'))
        report_interval = service.report_interval
        if report_interval:
            service.tg.add_timer(report_interval, self._report_state,
                                 report_interval, service)

    def is_up(self, service_ref):
        """Moved from nova.utils
        Check whether a service is up based on last heartbeat.
        """
        key = "%(topic)s:%(host)s" % service_ref
        return self.mc.get(str(key)) is not None

    def get_all(self, group_id):
        """
        Returns ALL members of the given group
        """
        LOG.debug(_('Memcached_Driver: get_all members of the %s group') %
                  group_id)
        rs = []
        ctxt = context.get_admin_context()
        services = self.conductor_api.service_get_all_by_topic(ctxt, group_id)
        for service in services:
            if self.is_up(service):
                rs.append(service['host'])
        return rs

    def _report_state(self, service):
        """Update the state of this service in the datastore."""
        ctxt = context.get_admin_context()
        try:
            key = "%(topic)s:%(host)s" % service.service_ref
            # memcached has data expiration time capability.
            # set(..., time=CONF.service_down_time) uses it and
            # reduces key-deleting code.
            self.mc.set(str(key),
                        timeutils.utcnow(),
                        time=CONF.service_down_time)

            # TODO(termie): make this pattern be more elegant.
            if getattr(service, 'model_disconnected', False):
                service.model_disconnected = False
                LOG.error(_('Recovered model server connection!'))

        # TODO(vish): this should probably only catch connection errors
        except Exception:  # pylint: disable=W0702
            if not getattr(service, 'model_disconnected', False):
                service.model_disconnected = True
                LOG.exception(_('model server went away'))
