# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012, Red Hat, Inc.
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

"""
Client side of the scheduler manager RPC API.
"""

from oslo.config import cfg

from nova.objects import base as objects_base
from nova.openstack.common import jsonutils
from nova import rpcclient

rpcapi_opts = [
    cfg.StrOpt('scheduler_topic',
               default='scheduler',
               help='the topic scheduler nodes listen on'),
]

CONF = cfg.CONF
CONF.register_opts(rpcapi_opts)

rpcapi_cap_opt = cfg.StrOpt('scheduler',
        help='Set a version cap for messages sent to scheduler services')
CONF.register_opt(rpcapi_cap_opt, 'upgrade_levels')


class SchedulerAPI(rpcclient.RpcProxy):
    '''Client side of the scheduler rpc API.

    API version history:

        1.0 - Initial version.
        1.1 - Changes to prep_resize():
                - remove instance_uuid, add instance
                - remove instance_type_id, add instance_type
                - remove topic, it was unused
        1.2 - Remove topic from run_instance, it was unused
        1.3 - Remove instance_id, add instance to live_migration
        1.4 - Remove update_db from prep_resize
        1.5 - Add reservations argument to prep_resize()
        1.6 - Remove reservations argument to run_instance()
        1.7 - Add create_volume() method, remove topic from live_migration()

        2.0 - Remove 1.x backwards compat
        2.1 - Add image_id to create_volume()
        2.2 - Remove reservations argument to create_volume()
        2.3 - Remove create_volume()
        2.4 - Change update_service_capabilities()
                - accepts a list of capabilities
        2.5 - Add get_backdoor_port()
        2.6 - Add select_hosts()

        ... Grizzly supports message version 2.6.  So, any changes to existing
        methods in 2.x after that point should be done such that they can
        handle the version_cap being set to 2.6.

        2.7 - Add select_destinations()
        2.8 - Deprecate prep_resize() -- JUST KIDDING.  It is still used
              by the compute manager for retries.
        2.9 - Added the legacy_bdm_in_spec parameter to run_instance()

        ... Havana supports message version 2.9.  So, any changes to existing
        methods in 2.x after that point should be done such that they can
        handle the version_cap being set to 2.9.

        ... - Deprecated live_migration() call, moved to conductor
        ... - Deprecated select_hosts()
    '''

    #
    # NOTE(russellb): This is the default minimum version that the server
    # (manager) side must implement unless otherwise specified using a version
    # argument to self.call()/cast()/etc. here.  It should be left as X.0 where
    # X is the current major API version (1.0, 2.0, ...).  For more information
    # about rpc API versioning, see the docs in
    # openstack/common/rpc/dispatcher.py.
    #
    BASE_RPC_API_VERSION = '2.0'

    VERSION_ALIASES = {
        'grizzly': '2.6',
        'havana': '2.9',
    }

    def __init__(self):
        version_cap = self.VERSION_ALIASES.get(CONF.upgrade_levels.scheduler,
                                               CONF.upgrade_levels.scheduler)
        super(SchedulerAPI, self).__init__(topic=CONF.scheduler_topic,
                default_version=self.BASE_RPC_API_VERSION,
                serializer=objects_base.NovaObjectSerializer(),
                version_cap=version_cap)
        self.client = self.get_client()

    def select_destinations(self, ctxt, request_spec, filter_properties):
        cctxt = self.client.prepare(version='2.7')
        return cctxt.call(ctxt, 'select_destinations',
            request_spec=request_spec, filter_properties=filter_properties)

    def run_instance(self, ctxt, request_spec, admin_password,
            injected_files, requested_networks, is_first_time,
            filter_properties, legacy_bdm_in_spec=True):
        version = '2.0'
        msg_kwargs = {'request_spec': request_spec,
                      'admin_password': admin_password,
                      'injected_files': injected_files,
                      'requested_networks': requested_networks,
                      'is_first_time': is_first_time,
                      'filter_properties': filter_properties}
        if self.client.can_send_version('2.9'):
            version = '2.9'
            msg_kwargs['legacy_bdm_in_spec'] = legacy_bdm_in_spec
        cctxt = self.client.prepare(version=version)
        return cctxt.cast(ctxt, 'run_instance', **msg_kwargs)

    def prep_resize(self, ctxt, instance, instance_type, image,
            request_spec, filter_properties, reservations):
        instance_p = jsonutils.to_primitive(instance)
        instance_type_p = jsonutils.to_primitive(instance_type)
        reservations_p = jsonutils.to_primitive(reservations)
        image_p = jsonutils.to_primitive(image)
        self.client.cast(ctxt, 'prep_resize',
                         instance=instance_p, instance_type=instance_type_p,
                         image=image_p, request_spec=request_spec,
                         filter_properties=filter_properties,
                         reservations=reservations_p)
