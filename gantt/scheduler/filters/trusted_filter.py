# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012 Intel, Inc.
# Copyright (c) 2011-2012 OpenStack Foundation
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

"""
Filter to add support for Trusted Computing Pools.

Filter that only schedules tasks on a host if the integrity (trust)
of that host matches the trust requested in the `extra_specs' for the
flavor.  The `extra_specs' will contain a key/value pair where the
key is `trust'.  The value of this pair (`trusted'/`untrusted') must
match the integrity of that host (obtained from the Attestation
service) before the task can be scheduled on that host.

Note that the parameters to control access to the Attestation Service
are in the `nova.conf' file in a separate `trust' section.  For example,
the config file will look something like:

    [DEFAULT]
    verbose=True
    ...
    [trust]
    server=attester.mynetwork.com

Details on the specific parameters can be found in the file `trust_attest.py'.

Details on setting up and using an Attestation Service can be found at
the Open Attestation project at:

    https://github.com/OpenAttestation/OpenAttestation
"""

import httplib
import socket
import ssl

from oslo.config import cfg

from nova import context
from nova import db
from nova.openstack.common.gettextutils import _
from nova.openstack.common import jsonutils
from nova.openstack.common import log as logging
from nova.openstack.common import timeutils

from gantt.scheduler import filters

LOG = logging.getLogger(__name__)

trusted_opts = [
    cfg.StrOpt('attestation_server',
               help='attestation server http'),
    cfg.StrOpt('attestation_server_ca_file',
               help='attestation server Cert file for Identity verification'),
    cfg.StrOpt('attestation_port',
               default='8443',
               help='attestation server port'),
    cfg.StrOpt('attestation_api_url',
               default='/OpenAttestationWebServices/V1.0',
               help='attestation web API URL'),
    cfg.StrOpt('attestation_auth_blob',
               help='attestation authorization blob - must change'),
    cfg.IntOpt('attestation_auth_timeout',
               default=60,
               help='Attestation status cache valid period length'),
]

CONF = cfg.CONF
trust_group = cfg.OptGroup(name='trusted_computing', title='Trust parameters')
CONF.register_group(trust_group)
CONF.register_opts(trusted_opts, group=trust_group)


class HTTPSClientAuthConnection(httplib.HTTPSConnection):
    """
    Class to make a HTTPS connection, with support for full client-based
    SSL Authentication
    """

    def __init__(self, host, port, key_file, cert_file, ca_file, timeout=None):
        httplib.HTTPSConnection.__init__(self, host,
                                         key_file=key_file,
                                         cert_file=cert_file)
        self.host = host
        self.port = port
        self.key_file = key_file
        self.cert_file = cert_file
        self.ca_file = ca_file
        self.timeout = timeout

    def connect(self):
        """
        Connect to a host on a given (SSL) port.
        If ca_file is pointing somewhere, use it to check Server Certificate.

        Redefined/copied and extended from httplib.py:1105 (Python 2.6.x).
        This is needed to pass cert_reqs=ssl.CERT_REQUIRED as parameter to
        ssl.wrap_socket(), which forces SSL to check server certificate
        against our client certificate.
        """
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file,
                                    ca_certs=self.ca_file,
                                    cert_reqs=ssl.CERT_REQUIRED)


class AttestationService(object):
    # Provide access wrapper to attestation server to get integrity report.

    def __init__(self):
        self.api_url = CONF.trusted_computing.attestation_api_url
        self.host = CONF.trusted_computing.attestation_server
        self.port = CONF.trusted_computing.attestation_port
        self.auth_blob = CONF.trusted_computing.attestation_auth_blob
        self.key_file = None
        self.cert_file = None
        self.ca_file = CONF.trusted_computing.attestation_server_ca_file
        self.request_count = 100

    def _do_request(self, method, action_url, body, headers):
        # Connects to the server and issues a request.
        # :returns: result data
        # :raises: IOError if the request fails

        action_url = "%s/%s" % (self.api_url, action_url)
        try:
            c = HTTPSClientAuthConnection(self.host, self.port,
                                          key_file=self.key_file,
                                          cert_file=self.cert_file,
                                          ca_file=self.ca_file)
            c.request(method, action_url, body, headers)
            res = c.getresponse()
            status_code = res.status
            if status_code in (httplib.OK,
                               httplib.CREATED,
                               httplib.ACCEPTED,
                               httplib.NO_CONTENT):
                return httplib.OK, res
            return status_code, None

        except (socket.error, IOError):
            return IOError, None

    def _request(self, cmd, subcmd, hosts):
        body = {}
        body['count'] = len(hosts)
        body['hosts'] = hosts
        cooked = jsonutils.dumps(body)
        headers = {}
        headers['content-type'] = 'application/json'
        headers['Accept'] = 'application/json'
        if self.auth_blob:
            headers['x-auth-blob'] = self.auth_blob
        status, res = self._do_request(cmd, subcmd, cooked, headers)
        if status == httplib.OK:
            data = res.read()
            return status, jsonutils.loads(data)
        else:
            return status, None

    def do_attestation(self, hosts):
        """Attests compute nodes through OAT service.

        :param hosts: hosts list to be attested
        :returns: dictionary for trust level and validate time
        """
        result = None

        status, data = self._request("POST", "PollHosts", hosts)
        if data != None:
            result = data.get('hosts')

        return result


class ComputeAttestationCache(object):
    """Cache for compute node attestation

    Cache compute node's trust level for sometime,
    if the cache is out of date, poll OAT service to flush the
    cache.

    OAT service may have cache also. OAT service's cache valid time
    should be set shorter than trusted filter's cache valid time.
    """

    def __init__(self):
        self.attestservice = AttestationService()
        self.compute_nodes = {}
        admin = context.get_admin_context()

        # Fetch compute node list to initialize the compute_nodes,
        # so that we don't need poll OAT service one by one for each
        # host in the first round that scheduler invokes us.
        computes = db.compute_node_get_all(admin)
        for compute in computes:
            service = compute['service']
            if not service:
                LOG.warn(_("No service for compute ID %s") % compute['id'])
                continue
            host = service['host']
            self._init_cache_entry(host)

    def _cache_valid(self, host):
        cachevalid = False
        if host in self.compute_nodes:
            node_stats = self.compute_nodes.get(host)
            if not timeutils.is_older_than(
                             node_stats['vtime'],
                             CONF.trusted_computing.attestation_auth_timeout):
                cachevalid = True
        return cachevalid

    def _init_cache_entry(self, host):
        self.compute_nodes[host] = {
            'trust_lvl': 'unknown',
            'vtime': timeutils.normalize_time(
                        timeutils.parse_isotime("1970-01-01T00:00:00Z"))}

    def _invalidate_caches(self):
        for host in self.compute_nodes:
            self._init_cache_entry(host)

    def _update_cache_entry(self, state):
        entry = {}

        host = state['host_name']
        entry['trust_lvl'] = state['trust_lvl']

        try:
            # Normalize as naive object to interoperate with utcnow().
            entry['vtime'] = timeutils.normalize_time(
                            timeutils.parse_isotime(state['vtime']))
        except ValueError:
            # Mark the system as un-trusted if get invalid vtime.
            entry['trust_lvl'] = 'unknown'
            entry['vtime'] = timeutils.utcnow()

        self.compute_nodes[host] = entry

    def _update_cache(self):
        self._invalidate_caches()
        states = self.attestservice.do_attestation(self.compute_nodes.keys())
        if states is None:
            return
        for state in states:
            self._update_cache_entry(state)

    def get_host_attestation(self, host):
        """Check host's trust level."""
        if host not in self.compute_nodes:
            self._init_cache_entry(host)
        if not self._cache_valid(host):
            self._update_cache()
        level = self.compute_nodes.get(host).get('trust_lvl')
        return level


class ComputeAttestation(object):
    def __init__(self):
        self.caches = ComputeAttestationCache()

    def is_trusted(self, host, trust):
        level = self.caches.get_host_attestation(host)
        return trust == level


class TrustedFilter(filters.BaseHostFilter):
    """Trusted filter to support Trusted Compute Pools."""

    def __init__(self):
        self.compute_attestation = ComputeAttestation()

    def host_passes(self, host_state, filter_properties):
        instance = filter_properties.get('instance_type', {})
        extra = instance.get('extra_specs', {})
        trust = extra.get('trust:trusted_host')
        host = host_state.host
        if trust:
            return self.compute_attestation.is_trusted(host, trust)
        return True
