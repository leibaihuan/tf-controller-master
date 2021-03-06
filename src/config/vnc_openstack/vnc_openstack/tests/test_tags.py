# Copyright 2019 Juniper Networks. All rights reserved.

import json
import time
from unittest import skip

import gevent
from tests import test_case
from vnc_api.exceptions import RefsExistError
from vnc_api.vnc_api import FloatingIp, FloatingIpPool
from vnc_api.vnc_api import IpamSubnetType, SubnetType
from vnc_api.vnc_api import LogicalRouter
from vnc_api.vnc_api import NetworkIpam, VnSubnetsType
from vnc_api.vnc_api import NetworkPolicy
from vnc_api.vnc_api import Project
from vnc_api.vnc_api import SecurityGroup
from vnc_api.vnc_api import Tag
from vnc_api.vnc_api import VirtualMachineInterface
from vnc_api.vnc_api import VirtualNetwork
from vnc_api.vnc_api import VirtualPortGroup
from vnc_openstack.neutron_plugin_db import (
    _NEUTRON_TAG_TO_SUBNETS,
    _SUBNET_TO_NEUTRON_TAGS
)


NO_TAG = 'no_tag'
TAG_RED = 'red'
TAG_BLUE = 'blue'
TAG_GREEN = 'green'
TAG_WHITE = 'white'
ALL_TAGS = [TAG_RED, TAG_BLUE, TAG_GREEN, TAG_WHITE]
PERFORMANCE_REPEAT = 10000  # how many times performance tests should be run


class NeutronTagsTestCase(test_case.NeutronBackendTestCase):
    def setUp(self, *args, **kwargs):
        super(NeutronTagsTestCase, self).setUp(*args, **kwargs)
        self.api = self._vnc_lib

        self.project = self._create_project()
        self.tags = self._create_tags()

    def tearDown(self):
        self._delete_tags()
        self._delete_project()
        super(NeutronTagsTestCase, self).tearDown()

    def _create_project(self):
        project_name = 'project-test-tags-{}'.format(self.id())
        try:
            self.api.project_create(Project(project_name))
        except RefsExistError:
            pass  # skip if already exist

        project_fq_name = ['default-domain', project_name]
        return self.api.project_read(fq_name=project_fq_name)

    def _delete_project(self):
        self.api.project_delete(fq_name=self.project.get_fq_name())

    def _create_tags(self):
        tags = {}
        for tag in ALL_TAGS:
            try:
                self.api.tag_create(Tag(tag_type_name='neutron_tag',
                                        tag_value=tag))
            except RefsExistError:
                pass  # skip if already exist

            tag_fq_name = ['neutron_tag={}'.format(tag)]
            tags[tag] = self.api.tag_read(fq_name=tag_fq_name)
        return tags

    def _delete_tags(self):
        for _, tag in self.tags.items():
            self.api.tag_delete(fq_name=tag.get_fq_name())

    def _get_tag(self, name):
        return self.tags[name]

    def assert_one_tag_full_match(self, resource_name, resources, tag):
        """Assert only one resource with full match single tag fetched.

        :param (str) resource_name: Name of resource to check
        :param (dict) resources: Dict with tag:vnc_resource pairs
        :param (str) tag: Name of tag to test
        """
        result = self.list_resource(
            resource_name,
            proj_uuid=self.project.uuid,
            req_filters={
                'tags': [tag],
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        # check virtual network count
        expected_count = 1
        self.assertEqual(expected_count, len(result))
        # check if virtual network uuid match
        self.assertEqual(resources[tag].uuid, result[0]['id'])
        # check if tags exist
        self.assertEqual(tag, result[0]['tags'][0])

    def assert_multiple_tags_full_match(self, resource_name, resource, tags):
        """Assert only one resource with full match multiple tags fetched.

        :param (str) resource_name: Name of resource to check
        :param (obj) resource: VNC resource object
        :param (list[str]) tags: List of tags to test
        """
        result = self.list_resource(
            resource_name,
            proj_uuid=self.project.uuid,
            req_filters={
                'tags': tags,
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        # check virtual network count
        expected_count = 1
        self.assertEqual(expected_count, len(result))
        # check if virtual network uuid match
        self.assertEqual(resource.uuid, result[0]['id'])
        # check if tags exist
        self.assertEqual(set(tags), set(result[0]['tags']))

    def assert_multiple_tags_any_match(self, resource_name, resources, tags):
        """Assert all resources with any tag match have been fetched.

        :param (str) resource_name: Name of resource to check
        :param (dict) resources: Dict with tag:vnc_resource pairs
        :param (list[str]) tags: List of tags to test
        """
        result = self.list_resource(
            resource_name,
            proj_uuid=self.project.uuid,
            req_filters={
                'tags-any': tags,
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        # check virtual network count
        expected_count = len(tags)
        self.assertEqual(expected_count, len(result))
        # check if virtual network uuid match
        expected_uuids = [resources[tag].uuid for tag in tags]
        for res in result:
            self.assertIn(res['id'], expected_uuids)
            self.assertGreaterEqual(len(res['tags']), 1)

    def assert_multiple_not_tags_match(self, resource_name, resources, tags):
        """Assert all resources with not-tag match have been fetched.

        :param (str) resource_name: Name of resource to check
        :param (dict) resources: Dict with tag:vnc_resource pairs
        :param (list[str]) tags: List of tags to test
        """
        result = self.list_resource(
            resource_name,
            proj_uuid=self.project.uuid,
            req_filters={
                'not-tags': tags,
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        # check virtual network count
        expected_count = len(ALL_TAGS) - len(tags)
        self.assertEqual(expected_count, len(result))
        # check if virtual network uuid match
        expected_uuids = [resources[tag].uuid for tag in
                          set(ALL_TAGS) - set(tags)]
        for res in result:
            self.assertIn(res['id'], expected_uuids)
            self.assertGreaterEqual(len(res['tags']), 1)

    def assert_multiple_not_tags_any_match(self, resource_name, resources,
                                           tags):
        """Assert all resources with not-tags-any match have been fetched.

        :param (str) resource_name: Name of resource to check
        :param (dict) resources: Dict with tag:vnc_resource pairs
        :param (list[str]) tags: List of tags to test
        """
        result = self.list_resource(
            resource_name,
            proj_uuid=self.project.uuid,
            req_filters={
                'not-tags-any': tags,
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        if len(tags) == 1:
            expected_count = len(ALL_TAGS) - 1
            expected_uuids = [resources[tag].uuid for tag in
                              set(ALL_TAGS) - set(tags)]
        else:
            expected_count = len(ALL_TAGS)
            expected_uuids = [resources[tag].uuid for tag in ALL_TAGS]
        # check virtual network count
        self.assertEqual(expected_count, len(result))
        # check if virtual network uuid match
        for res in result:
            self.assertIn(res['id'], expected_uuids)
            self.assertGreaterEqual(len(res['tags']), 1)

    def assert_tags_and_not_tags_single_res_match(self, resource_name,
                                                  resource, tags, not_tags):
        """Assert only one resource with match for both tags/not-tags filters.

        :param (str) resource_name: Name of resource to check
        :param (obj) resource: VNC resource object
        :param (list[str]) tags: List of tags to test
        :param (list[str]) not_tags: List of not_tags to test
        """
        result = self.list_resource(
            resource_name,
            proj_uuid=self.project.uuid,
            req_filters={
                'tags': tags,
                'not-tags': not_tags
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        # check virtual network count
        expected_count = 1
        self.assertEqual(expected_count, len(result))
        # check if virtual network uuid match
        self.assertEqual(resource.uuid, result[0]['id'])

    def assert_tags_and_not_tags_double_res_match(self, resource_name,
                                                  resources, tags, not_tags):
        """Assert two resources with match for both tags and not-tags filters.

        :param (str) resource_name: Name of resource to check
        :param (list) resources: list of VNC resource objects
        :param (list[str]) tags: List of tags to test
        :param (list[str]) not_tags: List of not_tags to test
        """
        result = self.list_resource(
            resource_name,
            proj_uuid=self.project.uuid,
            req_filters={
                'tags': tags,
                'not-tags': not_tags
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        # check virtual network count
        expected_count = 2
        self.assertEqual(expected_count, len(result))
        # check if virtual network uuid match
        expected_uuids = [res.uuid for res in resources]
        for res in result:
            self.assertIn(res['id'], expected_uuids)

    def assert_tags_exist(self, resource, expected_tags):
        tags = resource.get_tag_refs()
        self.assertEqual(len(tags), len(expected_tags))

        expected_tags_set = {'neutron_tag={}'.format(t) for t in expected_tags}
        given_tags_set = {t['to'][0] for t in tags}

        self.assertEqual(expected_tags_set, given_tags_set)


class TestVirtualNetworkNeutronTags(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestVirtualNetworkNeutronTags, self).setUp(*args, **kwargs)
        self._pre_create_virtual_networks()

    def tearDown(self):
        self._post_delete_virtual_networks()
        super(TestVirtualNetworkNeutronTags, self).tearDown()

    def _pre_create_virtual_networks(self):
        self.vns = {}
        for tag in ALL_TAGS:
            # create
            vn = VirtualNetwork('vn-{}-{}'.format(tag, self.id()),
                                parent_obj=self.project)
            vn.add_tag(self._get_tag(tag))
            vn.uuid = self.api.virtual_network_create(vn)
            # read
            self.vns[tag] = self.api.virtual_network_read(id=vn.uuid)

        # Create one virtual network without a tag
        vn_notag = VirtualNetwork('vn-{}-{}'.format(NO_TAG, self.id()),
                                  parent_obj=self.project)
        vn_notag.uuid = self.api.virtual_network_create(vn_notag)
        self.vns[NO_TAG] = self.api.virtual_network_read(id=vn_notag.uuid)

    def _post_delete_virtual_networks(self):
        for _, vn in self.vns.items():
            self.api.virtual_network_delete(id=vn.uuid)

    def test_list_tags_for_virtual_network(self):
        result = self.list_resource(
            'tags',
            proj_uuid=self.project.uuid,
            req_filters={
                'parent_id': self.vns[TAG_RED].uuid,
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        expected_length = 1
        self.assertEqual(expected_length, len(result))
        self.assertEqual(TAG_RED, result[0])

    def test_get_one_tag_for_virtual_network(self):
        body = {
            'context': {
                'operation': 'READ',
                'user_id': '',
                'is_admin': False,
                'roles': '',
                'tenant_id': self.project.uuid,
            },
            'data': {
                'filters': {
                    'parent_id': self.vns[TAG_RED].uuid,
                    'tag': TAG_RED,
                },
            },
        }
        resp = self._api_svr_app.post_json('/neutron/tags', body)
        result = json.loads(resp.text or 'null')
        # check if response is not empty
        self.assertIsNotNone(result)
        self.assertEqual(TAG_RED, result)

    def test_create_tag_for_virtual_network(self):
        tag = 'orange'
        vn = VirtualNetwork('vn-{}_{}'.format(tag, self.id()),
                            parent_obj=self.project)
        vn.uuid = self.api.virtual_network_create(vn)
        result = self.create_resource(
            'tags',
            self.project.uuid,
            extra_res_fields={
                'resource': {
                    'parent_id': vn.uuid,
                    'tags': [tag],
                },
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)
        expected_length = 1
        self.assertEqual(expected_length, len(result))
        self.assertEqual(tag, result[0])

        # fetch it back
        fetch_result = self.list_resource('network', self.project.uuid)
        self.assertIsNotNone(result)
        expected_length = 6  # 5 pre-created plus one from this test
        self.assertEqual(expected_length, len(fetch_result))
        for fetched_vn in fetch_result:
            if fetched_vn['id'] == vn.uuid:
                self.assertEqual(fetched_vn['tags'], [tag])
                break
        else:
            self.assertTrue(False, 'virtual network not fetchable')

        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=orange'])

    def test_delete_tag_from_virtual_network(self):
        vn_green = self.vns[TAG_GREEN]
        expected_len = 1
        self.assertEqual(expected_len, len(vn_green.get_tag_refs()))

        body = {
            'context': {
                'operation': 'DELETE',
                'user_id': '',
                'is_admin': False,
                'roles': '',
                'tenant_id': self.project.uuid,
            },
            'data': {
                'resource': {
                    'parent_id': vn_green.uuid,
                    'tag': TAG_GREEN,
                },
            },
        }
        self._api_svr_app.post_json('/neutron/tags', body)
        gevent.sleep(1)
        vn_green = self.api.virtual_network_read(id=vn_green.uuid)
        self.assertIsNone(vn_green.get_tag_refs())

    def test_delete_all_tags_from_virtual_network(self):
        vn_green = self.vns[TAG_GREEN]
        vn_green.add_tag(self.tags[TAG_RED])
        self.api.virtual_network_update(vn_green)
        gevent.sleep(1)
        vn_green = self.api.virtual_network_read(id=vn_green.uuid)

        expected_len = 2
        self.assertEqual(expected_len, len(vn_green.get_tag_refs()))

        body = {
            'context': {
                'operation': 'DELETEALL',
                'user_id': '',
                'is_admin': False,
                'roles': '',
                'tenant_id': self.project.uuid,
            },
            'data': {
                'resource': {
                    'parent_id': vn_green.uuid,
                },
            },
        }
        self._api_svr_app.post_json('/neutron/tags', body)
        gevent.sleep(1)
        vn_green = self.api.virtual_network_read(id=vn_green.uuid)
        self.assertIsNone(vn_green.get_tag_refs())

    def test_query_virtual_network_with_one_tag(self):
        """Query one by one, virtual networks filtering by tag."""
        for tag in ALL_TAGS:
            self.assert_one_tag_full_match(resource_name='network',
                                           resources=self.vns,
                                           tag=tag)

    def test_query_virtual_network_with_two_tags_full_match(self):
        """Query virtual networks filtering by multiple tags."""
        vn = VirtualNetwork('vn-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE,
                                                 self.id()))
        vn.add_tag(self._get_tag(TAG_BLUE))
        vn.add_tag(self._get_tag(TAG_WHITE))
        vn.uuid = self.api.virtual_network_create(vn)

        self.assert_multiple_tags_full_match(resource_name='network',
                                             resource=vn,
                                             tags=[TAG_BLUE, TAG_WHITE])
        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)

    def test_query_all_virtual_network_with_match_any(self):
        """Query virtual networks filtering by any tags."""
        tag_test_cases = [
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE],
            ALL_TAGS,
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_tags_any_match(resource_name='network',
                                                resources=self.vns,
                                                tags=tag_case)

    def test_query_all_virtual_network_with_match_not(self):
        """Query virtual networks filtering by not tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE]
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_match(resource_name='network',
                                                resources=self.vns,
                                                tags=tag_case)

    def test_query_all_virtual_network_with_match_not_any(self):
        """Query virtual networks filtering by not any tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_RED, TAG_WHITE],
            ALL_TAGS
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_any_match(resource_name='network',
                                                    resources=self.vns,
                                                    tags=tag_case)

    def test_query_virtual_network_with_tag_and_not_tag(self):
        """Query virtual networks filtering by both tags and not-tags."""
        vn = VirtualNetwork('vn-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE,
                                                 self.id()))
        vn.add_tag(self._get_tag(TAG_BLUE))
        vn.add_tag(self._get_tag(TAG_WHITE))
        vn.uuid = self.api.virtual_network_create(vn)

        self.assert_tags_and_not_tags_single_res_match(resource_name='network',
                                                       resource=self.vns[
                                                           TAG_BLUE],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_WHITE])
        self.assert_tags_and_not_tags_double_res_match(resource_name='network',
                                                       resources=[
                                                           self.vns[TAG_BLUE],
                                                           vn],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_GREEN])
        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)

    def test_query_virtual_network_with_multiple_filters(self):
        vn = VirtualNetwork('vn-multifilter-{}'.format(self.id()),
                            parent_obj=self.project,
                            is_shared=True,
                            router_external=True)
        vn.add_tag(self._get_tag(TAG_RED))
        vn.uuid = self.api.virtual_network_create(vn)

        test_cases = [
            {
                'req_filters': {
                    'tags': [TAG_RED],
                    'shared': True,
                    'router:external': True,
                },
                'expected_count': 2,
            },
            {
                'req_filters': {
                    'tags': [TAG_BLUE],
                    'shared': True,
                    'router:external': True,
                },
                'expected_count': 1,
            },
            {
                'req_filters': {
                    'tags': [TAG_BLUE],
                    'shared': True,
                    'router:external': False,
                },
                'expected_count': 1,
            },
            {
                'req_filters': {
                    'tags': ['orange', 'black'],
                    'shared': False,
                    'router:external': False,
                },
                'expected_count': 0,
            },
        ]
        for case in test_cases:
            result = self.list_resource(
                'network',
                proj_uuid=self.project.uuid,
                req_filters=case['req_filters']
            )
            self.assertEqual(case['expected_count'], len(result))

        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)

    def test_create_virtual_network_with_pre_created_tag(self):
        test_cases = [
            [TAG_RED],
            [TAG_BLUE, TAG_GREEN],
            [TAG_WHITE, TAG_BLUE, TAG_GREEN],
        ]
        for tags in test_cases:
            vn_dict = self.create_resource(
                'network',
                self.project.uuid,
                extra_res_fields={
                    'name': 'vn-{}-{}'.format(','.join(tags), self.id()),
                    'tags': tags,
                })

            vn = self.api.virtual_network_read(id=vn_dict['id'])
            self.assert_tags_exist(vn, tags)

            # cleanup
            self.api.virtual_network_delete(id=vn.uuid)

    def test_create_virtual_network_with_new_tag(self):
        tags = ['purple']

        vn_dict = self.create_resource(
            'network',
            self.project.uuid,
            extra_res_fields={
                'name': 'vn-{}-{}'.format(','.join(tags), self.id()),
                'tags': tags,
            })

        vn = self.api.virtual_network_read(id=vn_dict['id'])
        self.assert_tags_exist(vn, tags)

        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=purple'])

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_vn_by_one_tags_performance(self):
        """
        Test performance of querying VN by one tag.

        Average time should be about 8.38 milliseconds per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'network',
                proj_uuid=self.project.uuid,
                req_filters={
                    'tags': [TAG_RED],
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 10  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_vn_by_multiple_tags_performance(self):
        """
        Test performance of querying VN by multiple tag (full match).

        Average time should be about 5.58 ms per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'network',
                proj_uuid=self.project.uuid,
                req_filters={
                    'tags': [TAG_RED, TAG_BLUE, TAG_GREEN],
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 10  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_vn_by_multiple_any_tags_performance(self):
        """
        Test performance of querying VN by multiple tag (match any).

        Average time should be  about 13.77 milliseconds per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'network',
                proj_uuid=self.project.uuid,
                req_filters={
                    'tags-any': [TAG_RED, TAG_BLUE, TAG_GREEN],
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 20  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_vn_by_name_performance(self):
        """
        Test performance of querying VN by name.

        Average time should be about 25.45 ms per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'network',
                proj_uuid=self.project.uuid,
                req_filters={
                    'name': self.vns[TAG_RED].name,
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 30  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_vn_by_id_performance(self):
        """
        Test performance of querying VN by UUID.

        Average time should be about 47.34 ms per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'network',
                proj_uuid=self.project.uuid,
                req_filters={
                    'id': self.vns[TAG_RED].uuid,
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 55  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)


class TestFloatingIpNeutronTags(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestFloatingIpNeutronTags, self).setUp(*args, **kwargs)
        self._pre_create_virtual_network()
        self._pre_create_floating_ips()

    def tearDown(self):
        self._post_delete_floating_ips()
        self._post_delete_virtual_network()
        super(TestFloatingIpNeutronTags, self).tearDown()

    def _pre_create_virtual_network(self):
        self.ipam = NetworkIpam('ipam-{}'.format(self.id()))
        self.ipam.uuid = self.api.network_ipam_create(self.ipam)

        self.vn = VirtualNetwork('vn-forfip-{}'.format(self.id()),
                                 parent_obj=self.project)
        self.vn.add_network_ipam(self.ipam, VnSubnetsType([
            IpamSubnetType(SubnetType("192.168.7.0", 24))
        ]))
        self.vn.uuid = self.api.virtual_network_create(self.vn)

    def _post_delete_virtual_network(self):
        self.api.virtual_network_delete(id=self.vn.uuid)
        self.api.network_ipam_delete(id=self.ipam.uuid)

    def _pre_create_floating_ips(self):
        self.fip_pool = FloatingIpPool('fip-pool-{}'.format(self.id()),
                                       self.vn)
        self.fip_pool.uuid = self.api.floating_ip_pool_create(self.fip_pool)

        self.fips = {}
        for tag in ALL_TAGS:
            # create
            fip = FloatingIp("fip-{}-{}".format(tag, self.id()), self.fip_pool)
            fip.set_project(self.project)
            fip.add_tag(self._get_tag(tag))
            fip.uuid = self.api.floating_ip_create(fip)
            # read
            self.fips[tag] = self.api.floating_ip_read(id=fip.uuid)

    def _post_delete_floating_ips(self):
        for _, fip in self.fips.items():
            self.api.floating_ip_delete(id=fip.uuid)
        self.api.floating_ip_pool_delete(id=self.fip_pool.uuid)

    def test_query_floating_ip_with_one_tag(self):
        """Query one by one, floating IPs filtering by tag."""
        for tag in ALL_TAGS:
            self.assert_one_tag_full_match(resource_name='floatingip',
                                           resources=self.fips,
                                           tag=tag)

    def test_query_floating_ip_with_two_tags_full_match(self):
        """Query floating IPs filtering by multiple tags."""
        fip = FloatingIp("fip-{}_{}-{}".format(TAG_BLUE, TAG_WHITE,
                                               self.id()), self.fip_pool)
        fip.set_project(self.project)
        fip.add_tag(self._get_tag(TAG_BLUE))
        fip.add_tag(self._get_tag(TAG_WHITE))
        fip.uuid = self.api.floating_ip_create(fip)

        self.assert_multiple_tags_full_match(resource_name='floatingip',
                                             resource=fip,
                                             tags=[TAG_BLUE, TAG_WHITE])
        # cleanup
        self.api.floating_ip_delete(id=fip.uuid)

    def test_query_all_floating_ip_with_match_any(self):
        """Query floating IPs filtering by any tags."""
        tag_test_cases = [
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE],
            ALL_TAGS,
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_tags_any_match(resource_name='floatingip',
                                                resources=self.fips,
                                                tags=tag_case)

    def test_query_all_floating_ip_with_match_not_any(self):
        """Query floating IPs filtering by not any tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_RED, TAG_WHITE],
            ALL_TAGS
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_any_match(resource_name='floatingip',
                                                    resources=self.fips,
                                                    tags=tag_case)

    def test_query_all_floating_ip_with_match_not(self):
        """Query floating IPs filtering by not tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE]
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_match(resource_name='floatingip',
                                                resources=self.fips,
                                                tags=tag_case)

    def test_query_floating_ip_with_tag_and_not_tag(self):
        """Query floating IPs filtering by both tags and not-tags."""
        fip = FloatingIp("fip-{}_{}-{}".format(TAG_BLUE, TAG_WHITE,
                                               self.id()), self.fip_pool)
        fip.set_project(self.project)
        fip.add_tag(self._get_tag(TAG_BLUE))
        fip.add_tag(self._get_tag(TAG_WHITE))
        fip.uuid = self.api.floating_ip_create(fip)

        self.assert_tags_and_not_tags_single_res_match(
            resource_name='floatingip',
            resource=self.fips[TAG_BLUE],
            tags=[TAG_BLUE],
            not_tags=[TAG_WHITE])
        self.assert_tags_and_not_tags_double_res_match(
            resource_name='floatingip',
            resources=[
                self.fips[TAG_BLUE],
                fip],
            tags=[TAG_BLUE],
            not_tags=[TAG_GREEN])
        # cleanup
        self.api.floating_ip_delete(id=fip.uuid)

    def test_create_floating_ip_with_pre_created_tag(self):
        test_cases = [
            [TAG_RED],
            [TAG_BLUE, TAG_GREEN],
            [TAG_WHITE, TAG_BLUE, TAG_GREEN],
        ]
        for tags in test_cases:
            fip_dict = self.create_resource(
                'floatingip',
                self.project.uuid,
                extra_res_fields={
                    'name': 'fip-{}-{}'.format(','.join(tags), self.id()),
                    'tags': tags,
                    'project_id': self.project.uuid,
                    'floating_network_id': self.vn.uuid,
                })
            fip = self.api.floating_ip_read(id=fip_dict['id'])
            self.assert_tags_exist(fip, tags)

            # cleanup
            self.api.floating_ip_delete(id=fip.uuid)

    def test_create_floating_ip_with_new_tag(self):
        tags = ['purple']

        fip_dict = self.create_resource(
            'floatingip',
            self.project.uuid,
            extra_res_fields={
                'name': 'fip-{}-{}'.format(','.join(tags), self.id()),
                'tags': tags,
                'project_id': self.project.uuid,
                'floating_network_id': self.vn.uuid,
            })

        fip = self.api.floating_ip_read(id=fip_dict['id'])
        self.assert_tags_exist(fip, tags)

        # cleanup
        self.api.floating_ip_delete(id=fip.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=purple'])


class TestRouterNeutronTags(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestRouterNeutronTags, self).setUp(*args, **kwargs)
        self._pre_create_logical_routers()

    def tearDown(self):
        self._post_delete_logical_routers()
        super(TestRouterNeutronTags, self).tearDown()

    def _pre_create_logical_routers(self):
        self.lrs = {}
        for tag in ALL_TAGS:
            # create
            lr = LogicalRouter('lr-{}-{}'.format(tag, self.id()),
                               parent_obj=self.project)
            lr.add_tag(self._get_tag(tag))
            lr.uuid = self.api.logical_router_create(lr)
            self.lrs[tag] = self.api.logical_router_read(id=lr.uuid)

        # Create one logical router without a tag
        lr_notag = LogicalRouter('lr-{}-{}'.format(NO_TAG, self.id()),
                                 parent_obj=self.project)
        lr_notag.uuid = self.api.logical_router_create(lr_notag)
        self.lrs[NO_TAG] = self.api.logical_router_read(id=lr_notag.uuid)

    def _post_delete_logical_routers(self):
        for _, lr in self.lrs.items():
            self.api.logical_router_delete(id=lr.uuid)

    def test_query_logical_router_with_one_tag(self):
        """Query one by one, logical routers filtering by tag."""
        for tag in ALL_TAGS:
            self.assert_one_tag_full_match(resource_name='router',
                                           resources=self.lrs,
                                           tag=tag)

    def test_query_logical_router_with_two_tags_full_match(self):
        """Query logical routers filtering by multiple tags."""
        lr = LogicalRouter("lr-{}_{}-{}".format(TAG_BLUE, TAG_WHITE,
                                                self.id()),
                           parent_obj=self.project)
        lr.add_tag(self._get_tag(TAG_BLUE))
        lr.add_tag(self._get_tag(TAG_WHITE))
        lr.uuid = self.api.logical_router_create(lr)

        self.assert_multiple_tags_full_match(resource_name='router',
                                             resource=lr,
                                             tags=[TAG_BLUE, TAG_WHITE])
        # cleanup
        self.api.logical_router_delete(id=lr.uuid)

    def test_query_all_logical_routers_with_match_any(self):
        """Query logical routers filtering by any tags."""
        tag_test_cases = [
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE],
            ALL_TAGS,
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_tags_any_match(resource_name='router',
                                                resources=self.lrs,
                                                tags=tag_case)

    def test_query_all_logical_routers_with_match_not(self):
        """Query logical routers filtering by not tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE]
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_match(resource_name='router',
                                                resources=self.lrs,
                                                tags=tag_case)

    def test_query_all_logical_routers_with_match_not_any(self):
        """Query logical routers filtering by not any tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_RED, TAG_WHITE],
            ALL_TAGS
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_any_match(resource_name='router',
                                                    resources=self.lrs,
                                                    tags=tag_case)

    def test_query_logical_router_with_tag_and_not_tag(self):
        """Query logical routers filtering by both tags and not-tags."""
        lr = LogicalRouter("lr-{}_{}-{}".format(TAG_BLUE, TAG_WHITE,
                                                self.id()),
                           parent_obj=self.project)
        lr.add_tag(self._get_tag(TAG_BLUE))
        lr.add_tag(self._get_tag(TAG_WHITE))
        lr.uuid = self.api.logical_router_create(lr)

        self.assert_tags_and_not_tags_single_res_match(resource_name='router',
                                                       resource=self.lrs[
                                                           TAG_BLUE],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_WHITE])
        self.assert_tags_and_not_tags_double_res_match(resource_name='router',
                                                       resources=[
                                                           self.lrs[TAG_BLUE],
                                                           lr],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_GREEN])
        # cleanup
        self.api.logical_router_delete(id=lr.uuid)

    def test_create_logical_router_with_pre_created_tag(self):
        test_cases = [
            [TAG_RED],
            [TAG_BLUE, TAG_GREEN],
            [TAG_WHITE, TAG_BLUE, TAG_GREEN],
        ]
        for tags in test_cases:
            lr_dict = self.create_resource(
                'router',
                self.project.uuid,
                extra_res_fields={
                    'name': 'lr-{}-{}'.format(','.join(tags), self.id()),
                    'tags': tags,
                })

            lr = self.api.logical_router_read(id=lr_dict['id'])
            self.assert_tags_exist(lr, tags)

            # cleanup
            self.api.logical_router_delete(id=lr.uuid)

    def test_create_logical_router_with_new_tag(self):
        tags = ['purple']

        lr_dict = self.create_resource(
            'router',
            self.project.uuid,
            extra_res_fields={
                'name': 'lr-{}-{}'.format(','.join(tags), self.id()),
                'tags': tags,
            })

        lr = self.api.logical_router_read(id=lr_dict['id'])
        self.assert_tags_exist(lr, tags)

        # cleanup
        self.api.logical_router_delete(id=lr.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=purple'])


class TestPortNeutronTags(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestPortNeutronTags, self).setUp(*args, **kwargs)
        self._pre_create_virtual_network()
        self._pre_create_virtual_machine_interfaces()

    def tearDown(self):
        self._post_delete_virtual_machine_interfaces()
        self._post_delete_virtual_network()
        super(TestPortNeutronTags, self).tearDown()

    def _pre_create_virtual_network(self):
        vn_uuid = self.api.virtual_network_create(
            VirtualNetwork('vn-{}'.format(self.id()),
                           parent_obj=self.project))
        self.vn = self.api.virtual_network_read(id=vn_uuid)

    def _post_delete_virtual_network(self):
        self.api.virtual_network_delete(id=self.vn.uuid)

    def _pre_create_virtual_machine_interfaces(self):
        self.vmis = {}
        for tag in ALL_TAGS:
            # create
            vmi = VirtualMachineInterface(
                'vmi-{}-{}'.format(tag, self.id()), parent_obj=self.project)
            vmi.set_virtual_network(self.vn)
            vmi.add_tag(self._get_tag(tag))
            vmi.uuid = self.api.virtual_machine_interface_create(vmi)
            self.vmis[tag] = self.api.virtual_machine_interface_read(
                id=vmi.uuid)

        # Create one virtual machine interface without a tag
        vmi_notag = VirtualMachineInterface(
            'vmi-{}-{}'.format(NO_TAG, self.id()), parent_obj=self.project)
        vmi_notag.set_virtual_network(self.vn)
        vmi_notag.uuid = self.api.virtual_machine_interface_create(vmi_notag)
        self.vmis[NO_TAG] = self.api.virtual_machine_interface_read(
            id=vmi_notag.uuid)

    def _post_delete_virtual_machine_interfaces(self):
        for _, vmi in self.vmis.items():
            self.api.virtual_machine_interface_delete(id=vmi.uuid)

    def test_query_virtual_machine_interface_with_one_tag(self):
        """Query one by one, virtual machine interfaces filtering by tag."""
        for tag in ALL_TAGS:
            self.assert_one_tag_full_match(resource_name='port',
                                           resources=self.vmis,
                                           tag=tag)

    def test_query_virtual_machine_interfaces_with_two_tags_full_match(self):
        """Query virtual machine interfaces filtering by multiple tags."""
        vmi = VirtualMachineInterface(
            'vmi-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE, self.id()),
            parent_obj=self.project)
        vmi.set_virtual_network(self.vn)
        vmi.add_tag(self._get_tag(TAG_BLUE))
        vmi.add_tag(self._get_tag(TAG_WHITE))
        vmi.uuid = self.api.virtual_machine_interface_create(vmi)

        self.assert_multiple_tags_full_match(resource_name='port',
                                             resource=vmi,
                                             tags=[TAG_BLUE, TAG_WHITE])
        # cleanup
        self.api.virtual_machine_interface_delete(id=vmi.uuid)

    def test_query_all_virtual_machine_interface_with_match_any(self):
        """Query virtual machine interfaces filtering by any tags."""
        tag_test_cases = [
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE],
            ALL_TAGS,
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_tags_any_match(resource_name='port',
                                                resources=self.vmis,
                                                tags=tag_case)

    def test_query_all_virtual_machine_interface_with_match_not(self):
        """Query virtual machine interfaces filtering by not tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE]
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_match(resource_name='port',
                                                resources=self.vmis,
                                                tags=tag_case)

    def test_query_all_virtual_machine_interface_with_match_not_any(self):
        """Query virtual machine interfaces filtering by not any tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_RED, TAG_WHITE],
            ALL_TAGS
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_any_match(resource_name='port',
                                                    resources=self.vmis,
                                                    tags=tag_case)

    def test_query_virtual_machine_interfaces_with_tag_and_not_tag(self):
        """Query virtual machine i/fs filtering by both tags and not-tags."""
        vmi = VirtualMachineInterface(
            'vmi-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE, self.id()),
            parent_obj=self.project)
        vmi.set_virtual_network(self.vn)
        vmi.add_tag(self._get_tag(TAG_BLUE))
        vmi.add_tag(self._get_tag(TAG_WHITE))
        vmi.uuid = self.api.virtual_machine_interface_create(vmi)

        self.assert_tags_and_not_tags_single_res_match(resource_name='port',
                                                       resource=self.vmis[
                                                           TAG_BLUE],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_WHITE])
        self.assert_tags_and_not_tags_double_res_match(resource_name='port',
                                                       resources=[
                                                           self.vmis[TAG_BLUE],
                                                           vmi],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_GREEN])
        # cleanup
        self.api.virtual_machine_interface_delete(id=vmi.uuid)

    def test_create_virtual_machine_interface_with_pre_created_tag(self):
        test_cases = [
            [TAG_RED],
            [TAG_BLUE, TAG_GREEN],
            [TAG_WHITE, TAG_BLUE, TAG_GREEN],
        ]
        for tags in test_cases:
            vmi_dict = self.create_resource(
                'port',
                self.project.uuid,
                extra_res_fields={
                    'name': 'vmi-{}-{}'.format(','.join(tags), self.id()),
                    'tags': tags,
                    'network_id': self.vn.uuid,
                })

            vmi = self.api.virtual_machine_interface_read(id=vmi_dict['id'])
            self.assert_tags_exist(vmi, tags)

            # cleanup
            self.api.virtual_machine_interface_delete(id=vmi.uuid)

    def test_create_virtual_machine_interface_with_new_tag(self):
        tags = ['purple']

        vmi_dict = self.create_resource(
            'port',
            self.project.uuid,
            extra_res_fields={
                'name': 'vmi-{}-{}'.format(','.join(tags), self.id()),
                'tags': tags,
                'network_id': self.vn.uuid,
            })

        vmi = self.api.virtual_machine_interface_read(id=vmi_dict['id'])
        self.assert_tags_exist(vmi, tags)

        # cleanup
        self.api.virtual_machine_interface_delete(id=vmi.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=purple'])


class TestSecurityGroupNeutronTags(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestSecurityGroupNeutronTags, self).setUp(*args, **kwargs)
        self._pre_create_security_groups()

    def tearDown(self):
        self._post_delete_security_groups()
        super(TestSecurityGroupNeutronTags, self).tearDown()

    def _pre_create_security_groups(self):
        self.sgs = {}
        for tag in ALL_TAGS:
            # create
            sg = SecurityGroup('sg-{}-{}'.format(tag, self.id()),
                               parent_obj=self.project)
            sg.add_tag(self._get_tag(tag))
            sg.uuid = self.api.security_group_create(sg)
            self.sgs[tag] = self.api.security_group_read(id=sg.uuid)

        sg_notag = SecurityGroup('sg-{}-{}'.format(NO_TAG, self.id()),
                                 parent_obj=self.project)
        sg_notag.uuid = self.api.security_group_create(sg_notag)
        self.sgs[NO_TAG] = self.api.security_group_read(id=sg_notag.uuid)

    def _post_delete_security_groups(self):
        for _, sg in self.sgs.items():
            self.api.security_group_delete(id=sg.uuid)

    def test_query_security_group_with_one_tag(self):
        """Query one by one, security group filtering by tag."""
        for tag in ALL_TAGS:
            self.assert_one_tag_full_match(resource_name='security_group',
                                           resources=self.sgs,
                                           tag=tag)

    def test_query_security_group_with_two_tags_full_match(self):
        """Query security group filtering by multiple tags."""
        sg = SecurityGroup('sg-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE,
                                                self.id()),
                           parent_obj=self.project)
        sg.add_tag(self._get_tag(TAG_BLUE))
        sg.add_tag(self._get_tag(TAG_WHITE))
        sg.uuid = self.api.security_group_create(sg)

        self.assert_multiple_tags_full_match(resource_name='security_group',
                                             resource=sg,
                                             tags=[TAG_BLUE, TAG_WHITE])
        # cleanup
        self.api.security_group_delete(id=sg.uuid)

    def test_query_all_security_groups_with_match_any(self):
        """Query security groups filtering by any tags."""
        tag_test_cases = [
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE],
            ALL_TAGS,
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_tags_any_match(resource_name='security_group',
                                                resources=self.sgs,
                                                tags=tag_case)

    def test_query_all_security_groups_with_match_not(self):
        """Query security groups filtering by not tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE]
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_match(
                resource_name='security_group',
                resources=self.sgs,
                tags=tag_case)

    def test_query_all_security_groups_with_match_not_any(self):
        """Query security groups filtering by not any tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_RED, TAG_WHITE],
            ALL_TAGS
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_any_match(
                resource_name='security_group',
                resources=self.sgs,
                tags=tag_case)

    def test_query_security_group_with_tag_and_not_tag(self):
        """Query security group filtering by both tags and not-tags."""
        sg = SecurityGroup('sg-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE,
                                                self.id()),
                           parent_obj=self.project)
        sg.add_tag(self._get_tag(TAG_BLUE))
        sg.add_tag(self._get_tag(TAG_WHITE))
        sg.uuid = self.api.security_group_create(sg)

        self.assert_tags_and_not_tags_single_res_match(
            resource_name='security_group',
            resource=self.sgs[TAG_BLUE],
            tags=[TAG_BLUE],
            not_tags=[TAG_WHITE])
        self.assert_tags_and_not_tags_double_res_match(
            resource_name='security_group',
            resources=[self.sgs[TAG_BLUE],
                       sg],
            tags=[TAG_BLUE],
            not_tags=[TAG_GREEN])
        # cleanup
        self.api.security_group_delete(id=sg.uuid)

    def test_create_security_group_with_pre_created_tag(self):
        test_cases = [
            [TAG_RED],
            [TAG_BLUE, TAG_GREEN],
            [TAG_WHITE, TAG_BLUE, TAG_GREEN],
        ]
        for tags in test_cases:
            sg_dict = self.create_resource(
                'security_group',
                self.project.uuid,
                extra_res_fields={
                    'name': 'sg-{}-{}'.format(','.join(tags), self.id()),
                    'tags': tags,
                })

            sg = self.api.security_group_read(id=sg_dict['id'])
            self.assert_tags_exist(sg, tags)

            # cleanup
            self.api.security_group_delete(id=sg.uuid)

    def test_create_security_group_with_new_tag(self):
        tags = ['purple']

        sg_dict = self.create_resource(
            'security_group',
            self.project.uuid,
            extra_res_fields={
                'name': 'sg-{}-{}'.format(','.join(tags), self.id()),
                'tags': tags,
            })
        gevent.sleep(1)

        sg = self.api.security_group_read(id=sg_dict['id'])
        self.assert_tags_exist(sg, tags)

        # cleanup
        self.api.security_group_delete(id=sg.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=purple'])


class TestNetworkPolicyNeutronTags(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestNetworkPolicyNeutronTags, self).setUp(*args, **kwargs)
        self._pre_create_network_policies()

    def tearDown(self):
        self._post_delete_network_policies()
        super(TestNetworkPolicyNeutronTags, self).tearDown()

    def _pre_create_network_policies(self):
        self.nps = {}
        for tag in ALL_TAGS:
            # create
            np = NetworkPolicy('np-{}-{}'.format(tag, self.id()),
                               parent_obj=self.project)
            np.add_tag(self._get_tag(tag))
            np.uuid = self.api.network_policy_create(np)
            self.nps[tag] = self.api.network_policy_read(id=np.uuid)

        np_notag = NetworkPolicy('np-{}-{}'.format(NO_TAG, self.id()),
                                 parent_obj=self.project)
        np_notag.uuid = self.api.network_policy_create(np_notag)
        self.nps[NO_TAG] = self.api.network_policy_read(id=np_notag.uuid)

    def _post_delete_network_policies(self):
        for _, np in self.nps.items():
            self.api.network_policy_delete(id=np.uuid)

    def test_query_network_policy_with_one_tag(self):
        """Query one by one, network policy filtering by tag."""
        for tag in ALL_TAGS:
            self.assert_one_tag_full_match(resource_name='policy',
                                           resources=self.nps,
                                           tag=tag)

    def test_query_network_policy_with_two_tags_full_match(self):
        """Query network policy filtering by multiple tags."""
        np = NetworkPolicy('np-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE,
                                                self.id()),
                           parent_obj=self.project)
        np.add_tag(self._get_tag(TAG_BLUE))
        np.add_tag(self._get_tag(TAG_WHITE))
        np.uuid = self.api.network_policy_create(np)

        self.assert_multiple_tags_full_match(resource_name='policy',
                                             resource=np,
                                             tags=[TAG_BLUE, TAG_WHITE])
        # cleanup
        self.api.network_policy_delete(id=np.uuid)

    def test_query_all_network_policies_with_match_any(self):
        """Query network policies filtering by any tags."""
        tag_test_cases = [
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE],
            ALL_TAGS,
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_tags_any_match(resource_name='policy',
                                                resources=self.nps,
                                                tags=tag_case)

    def test_query_all_network_policies_with_match_not(self):
        """Query network policies filtering by not tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE]
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_match(resource_name='policy',
                                                resources=self.nps,
                                                tags=tag_case)

    def test_query_all_network_policies_with_match_not_any(self):
        """Query network policies filtering by not any tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_RED, TAG_WHITE],
            ALL_TAGS
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_any_match(resource_name='policy',
                                                    resources=self.nps,
                                                    tags=tag_case)

    def test_query_network_policy_with_tag_and_not_tag(self):
        """Query network policy filtering by both tags and not-tags."""
        np = NetworkPolicy('np-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE,
                                                self.id()),
                           parent_obj=self.project)
        np.add_tag(self._get_tag(TAG_BLUE))
        np.add_tag(self._get_tag(TAG_WHITE))
        np.uuid = self.api.network_policy_create(np)

        self.assert_tags_and_not_tags_single_res_match(resource_name='policy',
                                                       resource=self.nps[
                                                           TAG_BLUE],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_WHITE])
        self.assert_tags_and_not_tags_double_res_match(resource_name='policy',
                                                       resources=[
                                                           self.nps[TAG_BLUE],
                                                           np],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_GREEN])
        # cleanup
        self.api.network_policy_delete(id=np.uuid)

    def test_create_network_policy_with_pre_created_tag(self):
        test_cases = [
            [TAG_RED],
            [TAG_BLUE, TAG_GREEN],
            [TAG_WHITE, TAG_BLUE, TAG_GREEN],
        ]
        for tags in test_cases:
            np_dict = self.create_resource(
                'policy',
                self.project.uuid,
                extra_res_fields={
                    'name': 'np-{}-{}'.format(','.join(tags), self.id()),
                    'tags': tags,
                    'project_id': self.project.uuid,
                })

            np = self.api.network_policy_read(id=np_dict['id'])
            self.assert_tags_exist(np, tags)

            # cleanup
            self.api.network_policy_delete(id=np.uuid)

    def test_create_network_policy_with_new_tag(self):
        tags = ['purple']

        np_dict = self.create_resource(
            'policy',
            self.project.uuid,
            extra_res_fields={
                'name': 'np-{}-{}'.format(','.join(tags), self.id()),
                'tags': tags,
                'project_id': self.project.uuid,
            })

        np = self.api.network_policy_read(id=np_dict['id'])
        self.assert_tags_exist(np, tags)

        # cleanup
        self.api.network_policy_delete(id=np.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=purple'])


class TestVirtualPortGroupNeutronTags(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestVirtualPortGroupNeutronTags, self).setUp(*args, **kwargs)
        self._pre_create_virtual_network()
        self._pre_create_virtual_machine_interface()
        self._pre_create_virtual_port_groups()

    def tearDown(self):
        self._post_delete_virtual_machine_interface()
        self._post_delete_virtual_network()
        self._post_delete_virtual_port_groups()
        super(TestVirtualPortGroupNeutronTags, self).tearDown()

    def _pre_create_virtual_network(self):
        vn_uuid = self.api.virtual_network_create(
            VirtualNetwork('vn-{}'.format(self.id()),
                           parent_obj=self.project))
        self.vn = self.api.virtual_network_read(id=vn_uuid)

    def _post_delete_virtual_network(self):
        self.api.virtual_network_delete(id=self.vn.uuid)

    def _pre_create_virtual_machine_interface(self):
        vmi = VirtualMachineInterface('vmi-{}'.format(self.id()),
                                      parent_obj=self.project)
        vmi.set_virtual_network(self.vn)
        vmi.uuid = self.api.virtual_machine_interface_create(vmi)
        self.vmi = self.api.virtual_machine_interface_read(id=vmi.uuid)

    def _post_delete_virtual_machine_interface(self):
        self.api.virtual_machine_interface_delete(id=self.vmi.uuid)

    def _pre_create_virtual_port_groups(self):
        self.vpgs = {}
        for tag in ALL_TAGS:
            # create
            vpg = VirtualPortGroup('vpg-{}-{}'.format(tag, self.id()),
                                   parent_obj=self.project)
            vpg.set_virtual_port_group_trunk_port_id(self.vmi.uuid)
            vpg.add_tag(self._get_tag(tag))
            vpg.uuid = self.api.virtual_port_group_create(vpg)
            self.vpgs[tag] = self.api.virtual_port_group_read(id=vpg.uuid)

        vpg_notag = VirtualPortGroup('vpg-{}-{}'.format(NO_TAG, self.id()),
                                     parent_obj=self.project)
        vpg_notag.set_virtual_port_group_trunk_port_id(self.vmi.uuid)
        vpg_notag.uuid = self.api.virtual_port_group_create(vpg_notag)
        self.vpgs[NO_TAG] = self.api.virtual_port_group_read(id=vpg_notag.uuid)

    def _post_delete_virtual_port_groups(self):
        for _, vpg in self.vpgs.items():
            self.api.virtual_port_group_delete(id=vpg.uuid)

    def test_query_virtual_port_group_with_one_tag(self):
        """Query one by one, virtual port group filtering by tag."""
        for tag in ALL_TAGS:
            self.assert_one_tag_full_match(resource_name='trunk',
                                           resources=self.vpgs,
                                           tag=tag)

    def test_query_virtual_port_group_with_two_tags_full_match(self):
        """Query virtual port group filtering by multiple tags."""
        vpg = VirtualPortGroup('vpg-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE,
                                                     self.id()),
                               parent_obj=self.project)
        vpg.set_virtual_port_group_trunk_port_id(self.vmi.uuid)
        vpg.add_tag(self._get_tag(TAG_BLUE))
        vpg.add_tag(self._get_tag(TAG_WHITE))
        vpg.uuid = self.api.virtual_port_group_create(vpg)

        self.assert_multiple_tags_full_match(resource_name='trunk',
                                             resource=vpg,
                                             tags=[TAG_BLUE, TAG_WHITE])
        # cleanup
        self.api.ref_relax_for_delete(vpg.uuid, self.vmi.uuid)
        self.api.virtual_port_group_delete(id=vpg.uuid)

    def test_query_all_virtual_port_groups_with_match_any(self):
        """Query network policies filtering by any tags."""
        tag_test_cases = [
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE],
            ALL_TAGS,
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_tags_any_match(resource_name='trunk',
                                                resources=self.vpgs,
                                                tags=tag_case)

    def test_query_all_virtual_port_groups_with_match_not(self):
        """Query network policies filtering by not tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE]
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_match(resource_name='trunk',
                                                resources=self.vpgs,
                                                tags=tag_case)

    def test_query_all_virtual_port_groups_with_match_not_any(self):
        """Query network policies filtering by not any tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_RED, TAG_WHITE],
            ALL_TAGS
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_any_match(resource_name='trunk',
                                                    resources=self.vpgs,
                                                    tags=tag_case)

    def test_query_virtual_port_group_with_tag_and_not_tag(self):
        """Query virtual port group filtering by both tags and not-tags."""
        vpg = VirtualPortGroup('vpg-{}_{}-{}'.format(TAG_BLUE, TAG_WHITE,
                                                     self.id()),
                               parent_obj=self.project)
        vpg.set_virtual_port_group_trunk_port_id(self.vmi.uuid)
        vpg.add_tag(self._get_tag(TAG_BLUE))
        vpg.add_tag(self._get_tag(TAG_WHITE))
        vpg.uuid = self.api.virtual_port_group_create(vpg)

        self.assert_tags_and_not_tags_single_res_match(resource_name='trunk',
                                                       resource=self.vpgs[
                                                           TAG_BLUE],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_WHITE])
        self.assert_tags_and_not_tags_double_res_match(resource_name='trunk',
                                                       resources=[
                                                           self.vpgs[TAG_BLUE],
                                                           vpg],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_GREEN])
        # cleanup
        self.api.ref_relax_for_delete(vpg.uuid, self.vmi.uuid)
        self.api.virtual_port_group_delete(id=vpg.uuid)

    def test_create_virtual_port_group_with_pre_created_tag(self):
        test_cases = [
            [TAG_RED],
            [TAG_BLUE, TAG_GREEN],
            [TAG_WHITE, TAG_BLUE, TAG_GREEN],
        ]
        for tags in test_cases:
            vpg_dict = self.create_resource(
                'trunk',
                self.project.uuid,
                extra_res_fields={
                    'name': 'vpg-{}-{}'.format(','.join(tags), self.id()),
                    'tags': tags,
                    'port_id': self.vmi.uuid,
                })

            vpg = self.api.virtual_port_group_read(id=vpg_dict['id'])
            self.assert_tags_exist(vpg, tags)

            # cleanup
            vpg.del_virtual_machine_interface(self.vmi)
            self.api.virtual_port_group_update(vpg)
            self.api.ref_relax_for_delete(vpg.uuid, self.vmi.uuid)
            self.api.virtual_port_group_delete(id=vpg.uuid)

    def test_create_virtual_port_group_with_new_tag(self):
        tags = ['purple']

        vpg_dict = self.create_resource(
            'trunk',
            self.project.uuid,
            extra_res_fields={
                'name': 'vpg-{}-{}'.format(','.join(tags), self.id()),
                'tags': tags,
                'port_id': self.vmi.uuid,
            })

        vpg = self.api.virtual_port_group_read(id=vpg_dict['id'])
        self.assert_tags_exist(vpg, tags)

        # cleanup
        vpg.del_virtual_machine_interface(self.vmi)
        self.api.virtual_port_group_update(vpg)
        self.api.ref_relax_for_delete(vpg.uuid, self.vmi.uuid)
        self.api.virtual_port_group_delete(id=vpg.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=purple'])


class TestSubnetNeutronTags(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestSubnetNeutronTags, self).setUp(*args, **kwargs)
        self._pre_create_network_ipam()
        self._pre_create_virtual_networks_with_subnets()
        self._pre_create_kv_subnet_tags()

    def tearDown(self):
        self._post_delete_virtual_networks_with_subnets()
        self._post_delete_network_ipam()
        self._post_delete_kv_subnet_tags()
        super(TestSubnetNeutronTags, self).tearDown()

    def _pre_create_network_ipam(self):
        ipam_uuid = self.api.network_ipam_create(
            NetworkIpam('ipam-{}'.format(self.id())))
        self.ipam = self.api.network_ipam_read(id=ipam_uuid)

    def _post_delete_network_ipam(self):
        self.api.network_ipam_delete(id=self.ipam.uuid)

    def _pre_create_virtual_networks_with_subnets(self):
        self.vns = {}
        for n, tag in enumerate(ALL_TAGS):
            # create
            subnet_type = SubnetType('11.1.1.{}'.format(n), 24)
            ipam_sn_v4 = IpamSubnetType(subnet=subnet_type)

            vn = VirtualNetwork('vn-{}-{}'.format(tag, self.id()),
                                parent_obj=self.project)
            vn.add_network_ipam(self.ipam, VnSubnetsType([ipam_sn_v4]))
            vn.uuid = self.api.virtual_network_create(vn)
            # read
            self.vns[tag] = self.api.virtual_network_read(id=vn.uuid)

        # Create one virtual network without a tag
        vn_notag = VirtualNetwork('vn-{}-{}'.format(NO_TAG, self.id()),
                                  parent_obj=self.project)
        vn_notag.uuid = self.api.virtual_network_create(vn_notag)
        self.vns[NO_TAG] = self.api.virtual_network_read(id=vn_notag.uuid)

    def _post_delete_virtual_networks_with_subnets(self):
        for _, vn in self.vns.items():
            self.api.virtual_network_delete(id=vn.uuid)

    def _pre_create_kv_subnet_tags(self):
        self.sns = {}
        self.subnet_to_neutron_tags = {}
        self.neutron_tag_to_subnets = {}
        for tag in ALL_TAGS:
            # get subnet
            ipam_refs = self.vns[tag].get_network_ipam_refs()
            subnet = ipam_refs[0]['attr'].get_ipam_subnets()[0]
            subnet.uuid = subnet.subnet_uuid  # only for testing purposes
            self.sns[tag] = subnet
            # create kv
            neutron_tag = 'neutron_tag={}'.format(tag)
            self.subnet_to_neutron_tags[subnet.uuid] = [neutron_tag]
            self.neutron_tag_to_subnets[neutron_tag] = [subnet.uuid]

        # set kv
        self.api.kv_store(_SUBNET_TO_NEUTRON_TAGS,
                          json.dumps(self.subnet_to_neutron_tags))
        self.api.kv_store(_NEUTRON_TAG_TO_SUBNETS,
                          json.dumps(self.neutron_tag_to_subnets))

    def _post_delete_kv_subnet_tags(self):
        self.api.kv_delete(_SUBNET_TO_NEUTRON_TAGS)
        self.api.kv_delete(_NEUTRON_TAG_TO_SUBNETS)

    def test_query_subnet_with_one_tag(self):
        """Query one by one, subnets filtering by tag."""
        for tag in ALL_TAGS:
            self.assert_one_tag_full_match(resource_name='subnet',
                                           resources=self.sns,
                                           tag=tag)

    def test_query_subnet_with_two_tags_full_match(self):
        """Query subnets filtering by multiple tags."""
        # create virtual network with subnet
        subnet_type = SubnetType('11.11.11.0', 24)
        ipam_sn_v4 = IpamSubnetType(subnet=subnet_type)

        vn = VirtualNetwork('vn-{}'.format(self.id()), parent_obj=self.project)
        vn.add_network_ipam(self.ipam, VnSubnetsType([ipam_sn_v4]))
        vn.uuid = self.api.virtual_network_create(vn)
        vn = self.api.virtual_network_read(id=vn.uuid)

        ipam_refs = vn.get_network_ipam_refs()
        subnet = ipam_refs[0]['attr'].get_ipam_subnets()[0]
        subnet.uuid = subnet.subnet_uuid  # only for testing purposes

        # add subnet to kv neutron tags
        subnet_to_neutron_tags = self.subnet_to_neutron_tags
        neutron_tag_to_subnets = self.neutron_tag_to_subnets
        subnet_to_neutron_tags[subnet.uuid] = []
        for tag in [TAG_BLUE, TAG_WHITE]:
            neutron_tag = 'neutron_tag={}'.format(tag)
            neutron_tag_to_subnets[neutron_tag] = [subnet.uuid]
            subnet_to_neutron_tags[subnet.uuid].append(neutron_tag)
        # set kv
        self.api.kv_store(_SUBNET_TO_NEUTRON_TAGS,
                          json.dumps(subnet_to_neutron_tags))
        self.api.kv_store(_NEUTRON_TAG_TO_SUBNETS,
                          json.dumps(neutron_tag_to_subnets))

        self.assert_multiple_tags_full_match(resource_name='subnet',
                                             resource=subnet,
                                             tags=[TAG_BLUE, TAG_WHITE])
        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)

    def test_query_all_subnet_with_match_any(self):
        """Query subnets filtering by any tags."""
        tag_test_cases = [
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE],
            ALL_TAGS,
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_tags_any_match(resource_name='subnet',
                                                resources=self.sns,
                                                tags=tag_case)

    def test_query_all_subnet_with_match_not(self):
        """Query subnets filtering by not tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_GREEN, TAG_RED],
            [TAG_BLUE, TAG_RED, TAG_WHITE]
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_match(resource_name='subnet',
                                                resources=self.sns,
                                                tags=tag_case)

    def test_query_all_subnet_with_match_not_any(self):
        """Query subnets filtering by not any tags."""
        tag_test_cases = [
            [TAG_BLUE],
            [TAG_RED, TAG_WHITE],
            ALL_TAGS
        ]
        for tag_case in tag_test_cases:
            self.assert_multiple_not_tags_any_match(resource_name='subnet',
                                                    resources=self.sns,
                                                    tags=tag_case)

    def test_query_subnet_with_tag_and_not_tag(self):
        """Query subnets filtering by both tags and not-tags."""
        # create virtual network with subnet
        subnet_type = SubnetType('11.11.11.0', 24)
        ipam_sn_v4 = IpamSubnetType(subnet=subnet_type)

        vn = VirtualNetwork('vn-{}'.format(self.id()), parent_obj=self.project)
        vn.add_network_ipam(self.ipam, VnSubnetsType([ipam_sn_v4]))
        vn.uuid = self.api.virtual_network_create(vn)
        vn = self.api.virtual_network_read(id=vn.uuid)

        ipam_refs = vn.get_network_ipam_refs()
        subnet = ipam_refs[0]['attr'].get_ipam_subnets()[0]
        subnet.uuid = subnet.subnet_uuid

        # add subnet to kv neutron tags
        subnet_to_neutron_tags = self.subnet_to_neutron_tags
        neutron_tag_to_subnets = self.neutron_tag_to_subnets
        subnet_to_neutron_tags[subnet.uuid] = []
        for tag in [TAG_BLUE, TAG_WHITE]:
            neutron_tag = 'neutron_tag={}'.format(tag)
            neutron_tag_to_subnets[neutron_tag].append(subnet.uuid)
            subnet_to_neutron_tags[subnet.uuid].append(neutron_tag)
        # set kv
        self.api.kv_store(_SUBNET_TO_NEUTRON_TAGS,
                          json.dumps(subnet_to_neutron_tags))
        self.api.kv_store(_NEUTRON_TAG_TO_SUBNETS,
                          json.dumps(neutron_tag_to_subnets))

        self.assert_tags_and_not_tags_single_res_match(resource_name='subnet',
                                                       resource=self.sns[
                                                           TAG_BLUE],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_WHITE])
        self.assert_tags_and_not_tags_double_res_match(resource_name='subnet',
                                                       resources=[
                                                           self.sns[TAG_BLUE],
                                                           subnet],
                                                       tags=[TAG_BLUE],
                                                       not_tags=[TAG_GREEN])
        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)

    def test_create_subnet_with_pre_created_tag(self):
        vn = VirtualNetwork('vn-{}'.format(self.id()), parent_obj=self.project)
        vn.uuid = self.api.virtual_network_create(vn)
        vn = self.api.virtual_network_read(id=vn.uuid)

        test_cases = [
            [TAG_RED],
            [TAG_BLUE, TAG_GREEN],
            [TAG_WHITE, TAG_BLUE, TAG_GREEN],
        ]
        for n, tags in enumerate(test_cases):
            sn_dict = self.create_resource(
                'subnet',
                self.project.uuid,
                extra_res_fields={
                    'name': 'sn-{}-{}'.format(','.join(tags), self.id()),
                    'tags': tags,
                    'network_id': vn.uuid,
                    'cidr': '10.190.{}.0/24'.format(n),
                    'ip_version': 4,
                })

            tag_to_subnets = self.api.kv_retrieve(_NEUTRON_TAG_TO_SUBNETS)
            tag_to_subnets = json.loads(tag_to_subnets)
            for tag in tags:
                tag_name = 'neutron_tag={}'.format(tag)
                subnets = tag_to_subnets[tag_name]
                self.assertTrue(sn_dict['id'] in subnets)

        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)

    def test_create_subnet_with_new_tag(self):
        vn = VirtualNetwork('vn-{}'.format(self.id()), parent_obj=self.project)
        vn.uuid = self.api.virtual_network_create(vn)
        vn = self.api.virtual_network_read(id=vn.uuid)

        tags = ['purple']

        sn_dict = self.create_resource(
            'subnet',
            self.project.uuid,
            extra_res_fields={
                'name': 'sn-{}-{}'.format(','.join(tags), self.id()),
                'tags': tags,
                'network_id': vn.uuid,
                'cidr': '10.190.100.0/24',
                'ip_version': 4,
            })

        tag_to_subnets = self.api.kv_retrieve(_NEUTRON_TAG_TO_SUBNETS)
        tag_to_subnets = json.loads(tag_to_subnets)
        for tag in tags:
            tag_name = 'neutron_tag={}'.format(tag)
            subnets = tag_to_subnets[tag_name]
            self.assertTrue(sn_dict['id'] in subnets)

        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=purple'])

    def test_delete_tag_from_subnet(self):
        subnet_green = self.sns[TAG_GREEN]

        # ensure subnet green has only one tag 'green'
        result = self.list_resource(
            'tags',
            proj_uuid=self.project.uuid,
            req_filters={
                'parent_id': subnet_green.uuid,
            },
        )
        expected_length = 1
        self.assertEqual(expected_length, len(result))
        self.assertEqual(TAG_GREEN, result[0])

        # delete the tag
        body = {
            'context': {
                'operation': 'DELETE',
                'user_id': '',
                'is_admin': False,
                'roles': '',
                'tenant_id': self.project.uuid,
            },
            'data': {
                'resource': {
                    'parent_id': subnet_green.uuid,
                    'tag': TAG_GREEN,
                },
            },
        }
        self._api_svr_app.post_json('/neutron/tags', body)
        gevent.sleep(1)

        # check if subnet green has no tags
        result = self.list_resource(
            'tags',
            proj_uuid=self.project.uuid,
            req_filters={
                'parent_id': subnet_green.uuid,
            },
        )
        expected_length = 0
        self.assertEqual(expected_length, len(result))

    def test_delete_all_tags_from_subnet(self):
        subnet = self.sns[TAG_GREEN]
        tags = [TAG_GREEN, 'orange', 'purple']
        result = self.create_resource(
            'tags',
            self.project.uuid,
            extra_res_fields={
                'resource': {
                    'parent_id': subnet.uuid,
                    'tags': tags,
                }
            },
        )
        expected_length = 3
        self.assertEqual(expected_length, len(result))
        self.assertEqual(sorted(tags), sorted(result))

        body = {
            'context': {
                'operation': 'DELETEALL',
                'user_id': '',
                'is_admin': False,
                'roles': '',
                'tenant_id': self.project.uuid,
            },
            'data': {
                'resource': {
                    'parent_id': subnet.uuid,
                },
            },
        }
        self._api_svr_app.post_json('/neutron/tags', body)
        gevent.sleep(1)

        # check if subnet green has no tags
        result = self.list_resource(
            'tags',
            proj_uuid=self.project.uuid,
            req_filters={
                'parent_id': subnet.uuid,
            },
        )
        expected_length = 0
        self.assertEqual(expected_length, len(result))

        # cleanup
        self.api.tag_delete(fq_name=['neutron_tag=purple'])
        self.api.tag_delete(fq_name=['neutron_tag=orange'])

    def test_list_tags_for_subnet(self):
        result = self.list_resource(
            'tags',
            proj_uuid=self.project.uuid,
            req_filters={
                'parent_id': self.sns[TAG_RED].uuid,
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)

        expected_length = 1
        self.assertEqual(expected_length, len(result))
        self.assertEqual(TAG_RED, result[0])

    def test_get_one_tag_for_subnet(self):
        body = {
            'context': {
                'operation': 'READ',
                'user_id': '',
                'is_admin': False,
                'roles': '',
                'tenant_id': self.project.uuid,
            },
            'data': {
                'filters': {
                    'parent_id': self.sns[TAG_RED].uuid,
                    'tag': TAG_RED,
                },
            },
        }
        resp = self._api_svr_app.post_json('/neutron/tags', body)
        result = json.loads(resp.text or 'null')
        # check if response is not empty
        self.assertIsNotNone(result)
        self.assertEqual(TAG_RED, result)

    def test_create_tag_for_subnet(self):
        tag = 'orange'

        # create new virtual network with subnet
        subnet_type = SubnetType('10.10.111.0', 24)
        ipam_sn_v4 = IpamSubnetType(subnet=subnet_type)
        vn = VirtualNetwork('vn-{}_{}'.format(tag, self.id()),
                            parent_obj=self.project)
        vn.add_network_ipam(self.ipam, VnSubnetsType([ipam_sn_v4]))
        vn.uuid = self.api.virtual_network_create(vn)
        vn = self.api.virtual_network_read(id=vn.uuid)

        ipam_refs = vn.get_network_ipam_refs()
        subnet = ipam_refs[0]['attr'].get_ipam_subnets()[0]
        subnet.uuid = subnet.subnet_uuid  # only for testing purposes

        result = self.create_resource(
            'tags',
            self.project.uuid,
            extra_res_fields={
                'resource': {
                    'parent_id': subnet.uuid,
                    'tags': [tag],
                }
            },
        )
        # check if response is not empty
        self.assertIsNotNone(result)
        expected_length = 1
        self.assertEqual(expected_length, len(result))
        self.assertEqual(tag, result[0])

        # fetch it back
        fetch_result = self.list_resource('subnet', self.project.uuid)
        self.assertIsNotNone(result)
        expected_length = 5  # 4 pre-created plus one from this test
        self.assertEqual(expected_length, len(fetch_result))
        for fetched_subnet in fetch_result:
            if fetched_subnet['id'] == subnet.uuid:
                self.assertEqual(fetched_subnet['tags'][0], tag)
                break
        else:
            self.assertTrue(False, 'subnet not fetchable')

        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)
        self.api.tag_delete(fq_name=['neutron_tag=orange'])

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_subnet_by_one_tags_performance(self):
        """
        Test performance of querying VN by one tag.

        Average time should be about 8.17 ms per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'subnet',
                proj_uuid=self.project.uuid,
                req_filters={
                    'tags': [TAG_RED],
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 10  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_subnet_by_multiple_tags_performance(self):
        """
        Test performance of querying VN by multiple tag (full match).

        Average time should be about 5.20 ms per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'subnet',
                proj_uuid=self.project.uuid,
                req_filters={
                    'tags': [TAG_RED, TAG_BLUE, TAG_GREEN],
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 10  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_subnet_by_multiple_any_tags_performance(self):
        """
        Test performance of querying VN by multiple tag (match any).

        Average time should be about 15.38 ms per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'subnet',
                proj_uuid=self.project.uuid,
                req_filters={
                    'tags-any': [TAG_RED, TAG_BLUE, TAG_GREEN],
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 20  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)

    @skip('Long-lasting performance test. If necessary, turn it on manually.')
    def test_query_subnet_by_id_performance(self):
        """
        Test performance of querying VN by UUID.

        Average time should be about 5.58 ms per one request
        on machine with 4 cores CPU.
        """
        start = int(round(time.time() * 1000))
        for _ in range(PERFORMANCE_REPEAT):
            self.list_resource(
                'network',
                proj_uuid=self.project.uuid,
                req_filters={
                    'id': self.sns[TAG_RED].subnet_uuid,
                },
            )
        end = int(round(time.time() * 1000))

        avg_execution_time = (end - start) / PERFORMANCE_REPEAT
        expected_avg_execution_time = 60  # milliseconds
        self.assertLessEqual(avg_execution_time, expected_avg_execution_time)


class TestNeutronTagsPerms(NeutronTagsTestCase):
    def setUp(self, *args, **kwargs):
        super(TestNeutronTagsPerms, self).setUp(*args, **kwargs)

    def tearDown(self):
        super(TestNeutronTagsPerms, self).tearDown()

    def test_tag_default_perms(self):
        PERMS_RX = 5
        tag = 'orange'

        vn = VirtualNetwork('vn-{}_{}'.format(tag, self.id()),
                            parent_obj=self.project)
        vn.uuid = self.api.virtual_network_create(vn)
        self.create_resource(
            'tags',
            self.project.uuid,
            extra_res_fields={
                'resource': {
                    'parent_id': vn.uuid,
                    'tags': [tag],
                },
            },
        )

        tag_fq_name = ['neutron_tag={}'.format(tag)]
        tag_obj = self.api.tag_read(fq_name=tag_fq_name)
        self.assertEqual(tag_obj.perms2.global_access, PERMS_RX)
        self.assertEqual(tag_obj.perms2.owner, 'cloud-admin')

        # cleanup
        self.api.virtual_network_delete(id=vn.uuid)
        self.api.tag_delete(id=tag_obj.uuid)
