#    Copyright 2013 IBM Corp.
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

import datetime
import uuid

from nova.objects import fields
from nova.objects import instance as instance_obj
from nova.objects import instance_fault as inst_fault_obj


def fake_db_secgroups(instance, names):
    secgroups = []
    for i, name in enumerate(names):
        group_name = 'secgroup-%i' % i
        if isinstance(name, dict) and name.get('name'):
            group_name = name.get('name')
        secgroups.append(
            {'id': i,
             'instance_uuid': instance['uuid'],
             'name': group_name,
             'description': 'Fake secgroup',
             'user_id': instance['user_id'],
             'project_id': instance['project_id'],
             'deleted': False,
             'deleted_at': None,
             'created_at': None,
             'updated_at': None,
             })
    return secgroups


def fake_db_instance(**updates):
    db_instance = {
        'id': 1,
        'deleted': False,
        'uuid': str(uuid.uuid4()),
        'user_id': 'fake-user',
        'project_id': 'fake-project',
        'host': 'fake-host',
        'created_at': datetime.datetime(1955, 11, 5),
        'pci_devices': [],
        'security_groups': [],
        'metadata': {},
        'system_metadata': {},
        'root_gb': 0,
        'ephemeral_gb': 0
        }

    for name, field in instance_obj.Instance.fields.items():
        if name in db_instance:
            continue
        if field.nullable:
            db_instance[name] = None
        elif field.default != fields.UnspecifiedDefault:
            db_instance[name] = field.default
        else:
            raise Exception('fake_db_instance needs help with %s' % name)

    if updates:
        db_instance.update(updates)

    if db_instance.get('security_groups'):
        db_instance['security_groups'] = fake_db_secgroups(
            db_instance, db_instance['security_groups'])

    return db_instance


def fake_instance_obj(context, **updates):
    expected_attrs = updates.pop('expected_attrs', None)
    return instance_obj.Instance._from_db_object(context,
               instance_obj.Instance(), fake_db_instance(**updates),
               expected_attrs=expected_attrs)


def fake_fault_obj(instance_uuid, code=404,
                   message='HTTPNotFound',
                   details='Stock details for test',
                   **updates):
    fault = {
        'id': 1,
        'instance_uuid': instance_uuid,
        'code': code,
        'message': message,
        'details': details,
        'host': 'fake_host',
        'deleted': False,
        'created_at': datetime.datetime(2010, 10, 10, 12, 0, 0),
        'updated_at': None,
        'deleted_at': None
    }
    if updates:
        fault.update(updates)
    return inst_fault_obj.InstanceFault._from_db_object(
                                           inst_fault_obj.InstanceFault(),
                                           fault)
