# Copyright (c) 2012 OpenStack Foundation
# All Rights Reserved.
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

from oslo.config import cfg

from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging

from gantt.scheduler import filters
from gantt import servicegroup

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class ComputeFilter(filters.BaseHostFilter):
    """Filter on active Compute nodes."""

    def __init__(self):
        self.servicegroup_api = servicegroup.API()

    # Host state does not change within a request
    run_filter_once_per_request = True

    def host_passes(self, host_state, filter_properties):
        """Returns True for only active compute nodes."""
        service = host_state.service
        if service['disabled']:
            LOG.debug(_("%(host_state)s is disabled, reason: %(reason)s"),
                      {'host_state': host_state,
                       'reason': service.get('disabled_reason')})
            return False
        else:
            if not self.servicegroup_api.service_is_up(service):
                LOG.warn(_("%(host_state)s has not been heard from in a "
                           " while"), {'host_state': host_state})
                return False
        return True
