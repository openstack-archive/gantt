# Copyright (c) 2013 ISP RAS.
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

from nova.scheduler import filters


class PciPassthroughFilter(filters.BaseHostFilter):
    """Pci Passthrough Filter based on PCI request

    Filter that schedules instances on a host if the host has devices
    to meet the device requests in the 'extra_specs' for the flavor.

    PCI resource tracker provides updated summary information about the
    PCI devices for each host, like:
    [{"count": 5, "vendor_id": "8086", "product_id": "1520",
        "extra_info":'{}'}],
    and VM requests PCI devices via PCI requests, like:
    [{"count": 1, "vendor_id": "8086", "product_id": "1520",}].

    The filter checks if the host passes or not based on this information.
    """

    def host_passes(self, host_state, filter_properties):
        """Return true if the host has the required PCI devices."""
        if not filter_properties.get('pci_requests'):
            return True
        return host_state.pci_stats.support_requests(
            filter_properties.get('pci_requests'))
