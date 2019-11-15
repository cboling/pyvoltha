#
# Copyright 2017 the original author or authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from __future__ import absolute_import
from __future__ import print_function
from unittest import TestCase, main
from binascii import unhexlify

from pyvoltha.adapters.extensions.omci.omci import *
from six.moves import range
import codecs


def hexify(frame):
    """Return a hexadecimal string encoding of input buffer"""
    return codecs.encode(bytes(frame),'hex')


def hex2raw(hex_string):
    """ convert a string or bytes containing a hexadecimal as raw bytes"""
    return codecs.decode(hex_string,'hex')


def chunk(indexable, chunk_size):
    for i in range(0, len(indexable), chunk_size):
        yield indexable[i:i + chunk_size]


class TestOmciFundamentals(TestCase):

    def test_bitpos_from_mask(self):

        f = lambda x: bitpos_from_mask(x)
        self.assertEqual(f(0), [])
        self.assertEqual(f(1), [0])
        self.assertEqual(f(3), [0, 1])
        self.assertEqual(f(255), [0, 1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(f(0x800), [11])
        self.assertEqual(f(0x811), [0, 4, 11])

        f = lambda x: bitpos_from_mask(x, 16, -1)
        self.assertEqual(f(0), [])
        self.assertEqual(f(1), [16])
        self.assertEqual(f(0x800), [5])
        self.assertEqual(f(0x801), [5, 16])


    def test_attribute_indeices_from_mask(self):

        f = EntityClass.attribute_indices_from_mask
        self.assertEqual(f(0), [])
        self.assertEqual(f(0x800), [5])
        self.assertEqual(f(0xf000), [1, 2, 3, 4])
        self.assertEqual(f(0xf804), [1, 2, 3, 4, 5, 14])

    def test_entity_attribute_serialization(self):

        e = CircuitPack(vendor_id='F')
        self.assertEqual(e.serialize(), b'F\x00\x00\x00')

        e = CircuitPack(vendor_id='FOOX')
        self.assertEqual(e.serialize(), b'FOOX')

        e = CircuitPack(vendor_id='FOOX', number_of_ports=16)
        self.assertEqual(e.serialize(), b'\x10FOOX')

    def test_entity_attribute_serialization_mask_based(self):

        e = CircuitPack(
            number_of_ports=4,
            serial_number=b'BCMX31323334', # serial number is 4 ascii + 4 hex. 8 octets on the wire
            version=b'a1c12fba91de',
            vendor_id=b'BCM',
            total_tcont_buffer_number=128
        )

        # Full object
        self.assertEqual(e.serialize(),
                         b'\x04BCMX1234a1c12fba91de\x00\x00BCM\x00\x80')

        # Explicit mask with valid values
        self.assertEqual(e.serialize(0x800), b'BCM\x00')
        self.assertEqual(e.serialize(0x6800), b'\x04BCMX1234BCM\x00')

        # Referring to an unfilled field is regarded as error
        self.assertRaises(OmciUninitializedFieldError, e.serialize, 0xc00)

    def test_omci_mask_value_gen(self):
        cls = CircuitPack
        self.assertEqual(cls.mask_for('vendor_id'), 0x800)
        self.assertEqual(
            cls.mask_for('vendor_id', 'bridged_or_ip_ind'), 0x900)

    reference_get_request_hex = (
        b'0000490a'
        b'00060101'
        b'08000000'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000028'
    )
    reference_get_request_raw = hex2raw(reference_get_request_hex)

    reference_get_response_hex = (
        b'0000290a'
        b'00060101'
        b'00080050'
        b'4d435300'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000000'
        b'00000028'
    )
    reference_get_response_raw = hex2raw(reference_get_response_hex)

    def test_omci_frame_serialization(self):

        frame = OmciFrame(
            transaction_id=0,
            message_type=OmciGet.message_id,
            omci_message=OmciGet(
                entity_class=CircuitPack.class_id,
                entity_id=0x101,
                attributes_mask=CircuitPack.mask_for('vendor_id')
            )
        )
        self.assertEqual(hexify(frame), self.reference_get_request_hex)

    def test_omci_frame_deserialization_no_data(self):
        frame = OmciFrame(self.reference_get_request_raw)
        self.assertEqual(frame.transaction_id, 0)
        self.assertEqual(frame.message_type, 0x49)
        self.assertEqual(frame.omci, 10)
        self.assertEqual(frame.omci_message.entity_class, 0x6)
        self.assertEqual(frame.omci_message.entity_id, 0x101)
        self.assertEqual(frame.omci_message.attributes_mask, 0x800)
        self.assertEqual(frame.omci_trailer, 0x28)

    def test_omci_frame_deserialization_with_data(self):
        frame = OmciFrame(self.reference_get_response_raw)
        self.assertEqual(frame.transaction_id, 0)
        self.assertEqual(frame.message_type, 0x29)
        self.assertEqual(frame.omci, 10)
        self.assertEqual(frame.omci_message.success_code, 0x0)
        self.assertEqual(frame.omci_message.entity_class, 0x6)
        self.assertEqual(frame.omci_message.entity_id, 0x101)
        self.assertEqual(frame.omci_message.attributes_mask, 0x800)
        self.assertEqual(frame.omci_trailer, 0x28)

    def test_entity_attribute_deserialization(self):
        pass


class TestSelectMessageGeneration(TestCase):

    def assertGeneratedFrameEquals(self, frame, ref):
        assert isinstance(frame, Packet)
        serialized_hexified_frame = hexify(frame).upper()
        ref = ref.upper()
        if serialized_hexified_frame != ref:
            self.fail('Mismatch:\nReference:\n{}\nGenerated (bad):\n{}'.format(
                ref, serialized_hexified_frame
            ))

    def test_mib_reset_message_serialization(self):
        ref = b'00014F0A000200000000000000000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=1,
            message_type=OmciMibReset.message_id,
            omci_message=OmciMibReset(
                entity_class=OntData.class_id
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_gal_ethernet_profile(self):
        ref = b'0002440A011000010030000000000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=2,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=GalEthernetProfile.class_id,
                entity_id=1,
                data=dict(
                    max_gem_payload_size=48
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_set_tcont_1(self):
        ref = b'0003480A010680008000040000000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        data = dict(
            alloc_id=0x400
        )
        frame = OmciFrame(
            transaction_id=3,
            message_type=OmciSet.message_id,
            omci_message=OmciSet(
                entity_class=Tcont.class_id,
                entity_id=0x8000,
                attributes_mask=Tcont.mask_for(*list(data.keys())),
                data=data
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_set_tcont_2(self):
        ref = b'0004480A010680018000040100000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        data = dict(
            alloc_id=0x401
        )
        frame = OmciFrame(
            transaction_id=4,
            message_type=OmciSet.message_id,
            omci_message=OmciSet(
                entity_class=Tcont.class_id,
                entity_id=0x8001,
                attributes_mask=Tcont.mask_for(*list(data.keys())),
                data=data
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_8021p_mapper_service_profile(self):
        ref = b'0007440A00828000ffffffffffffffff' \
              b'ffffffffffffffffffff000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=7,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=Ieee8021pMapperServiceProfile.class_id,
                entity_id=0x8000,
                data=dict(
                    tp_pointer=OmciNullPointer,
                    interwork_tp_pointer_for_p_bit_priority_0=OmciNullPointer,
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_mac_bridge_service_profile(self):
        ref = b'000B440A002D02010001008000140002' \
              b'000f0001000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=11,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=MacBridgeServiceProfile.class_id,
                entity_id=0x201,
                data=dict(
                    spanning_tree_ind=False,
                    learning_ind=True,
                    priority=0x8000,
                    max_age=20 * 256,
                    hello_time=2 * 256,
                    forward_delay=15 * 256,
                    unknown_mac_address_discard=True
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_gem_port_network_ctp(self):
        ref = b'000C440A010C01000400800003010000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=12,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=GemPortNetworkCtp.class_id,
                entity_id=0x100,
                data=dict(
                    port_id=0x400,
                    tcont_pointer=0x8000,
                    direction=3,
                    traffic_management_pointer_upstream=0x100
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_multicast_gem_interworking_tp(self):
        ref = b'0011440A011900060104000001000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=17,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=MulticastGemInterworkingTp.class_id,
                entity_id=0x6,
                data=dict(
                    gem_port_network_ctp_pointer=0x104,
                    interworking_option=0,
                    service_profile_pointer=0x1,
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_gem_inteworking_tp(self):
        ref = b'0012440A010A80010100058000000000' \
              b'01000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=18,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=GemInterworkingTp.class_id,
                entity_id=0x8001,
                data=dict(
                    gem_port_network_ctp_pointer=0x100,
                    interworking_option=5,
                    service_profile_pointer=0x8000,
                    interworking_tp_pointer=0x0,
                    gal_profile_pointer=0x1
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_set_8021p_mapper_service_profile(self):
        ref = b'0016480A008280004000800100000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        data = dict(
            interwork_tp_pointer_for_p_bit_priority_0=0x8001
        )
        frame = OmciFrame(
            transaction_id=22,
            message_type=OmciSet.message_id,
            omci_message=OmciSet(
                entity_class=Ieee8021pMapperServiceProfile.class_id,
                entity_id=0x8000,
                attributes_mask=Ieee8021pMapperServiceProfile.mask_for(
                    *list(data.keys())),
                data=data
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_mac_bridge_port_configuration_data(self):
        ref = b'001A440A002F21010201020380000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=26,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=MacBridgePortConfigurationData.class_id,
                entity_id=0x2101,
                data=dict(
                    bridge_id_pointer=0x201,
                    port_num=2,
                    tp_type=3,
                    tp_pointer=0x8000
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_vlan_tagging_filter_data(self):
        ref = b'001F440A005421010400000000000000' \
              b'00000000000000000000000000000000' \
              b'100100000000000000000028'
        vlan_filter_list = [0] * 12
        vlan_filter_list[0] = 0x0400

        frame = OmciFrame(
            transaction_id=31,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=VlanTaggingFilterData.class_id,
                entity_id=0x2101,
                data=dict(
                    vlan_filter_list=vlan_filter_list,
                    forward_operation=0x10,
                    number_of_entries=1
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_extended_vlan_tagging_operation_configuration_data(self):
        ref = b'0023440A00AB02020A04010000000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=35,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=
                    ExtendedVlanTaggingOperationConfigurationData.class_id,
                entity_id=0x202,
                data=dict(
                    association_type=10,
                    associated_me_pointer=0x401
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_set_extended_vlan_tagging_operation_configuration_data(self):
        ref = b'0024480A00AB02023800810081000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        data = dict(
            input_tpid=0x8100,
            output_tpid=0x8100,
            downstream_mode=0,  # inverse of upstream
        )
        frame = OmciFrame(
            transaction_id=36,
            message_type=OmciSet.message_id,
            omci_message=OmciSet(
                entity_class=\
                    ExtendedVlanTaggingOperationConfigurationData.class_id,
                entity_id=0x202,
                attributes_mask= \
                    ExtendedVlanTaggingOperationConfigurationData.mask_for(
                        *list(data.keys())),
                data=data
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_set_extended_vlan_tagging_1(self):
        ref = b'0025480A00AB02020400f00000008200' \
              b'5000402f000000082004000000000000' \
              b'000000000000000000000028'
        data = dict(
            received_frame_vlan_tagging_operation_table=\
                VlanTaggingOperation(
                    filter_outer_priority=15,
                    filter_inner_priority=8,
                    filter_inner_vid=1024,
                    filter_inner_tpid_de=5,
                    filter_ether_type=0,
                    treatment_tags_to_remove=1,
                    pad3=2,
                    treatment_outer_priority=15,
                    treatment_inner_priority=8,
                    treatment_inner_vid=1024,
                    treatment_inner_tpid_de=4
                )
        )
        frame = OmciFrame(
            transaction_id=37,
            message_type=OmciSet.message_id,
            omci_message=OmciSet(
                entity_class=\
                    ExtendedVlanTaggingOperationConfigurationData.class_id,
                entity_id=0x202,
                attributes_mask= \
                    ExtendedVlanTaggingOperationConfigurationData.mask_for(
                        *list(data.keys())),
                data=data
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_set_extended_vlan_tagging_2(self):
        ref = b'0026480A00AB02020400F00000008200' \
              b'd000402f00000008200c000000000000' \
              b'000000000000000000000028'
        data = dict(
            received_frame_vlan_tagging_operation_table=
                VlanTaggingOperation(
                    filter_outer_priority=15,
                    filter_inner_priority=8,
                    filter_inner_vid=1025,
                    filter_inner_tpid_de=5,
                    filter_ether_type=0,
                    treatment_tags_to_remove=1,
                    pad3=2,
                    treatment_outer_priority=15,
                    treatment_inner_priority=8,
                    treatment_inner_vid=1025,
                    treatment_inner_tpid_de=4
                )
        )
        frame = OmciFrame(
            transaction_id=38,
            message_type=OmciSet.message_id,
            omci_message=OmciSet(
                entity_class=
                    ExtendedVlanTaggingOperationConfigurationData.class_id,
                entity_id=0x202,
                attributes_mask=
                    ExtendedVlanTaggingOperationConfigurationData.mask_for(
                        *list(data.keys())),
                data=data
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_create_mac_bridge_port_configuration_data2(self):
        ref = b'0029440A002F02010201010b04010000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=41,
            message_type=OmciCreate.message_id,
            omci_message=OmciCreate(
                entity_class=MacBridgePortConfigurationData.class_id,
                entity_id=0x201,
                data=dict(
                    bridge_id_pointer=0x201,
                    encapsulation_methods=0,
                    port_num=1,
                    port_priority=0,
                    port_path_cost=0,
                    port_spanning_tree_in=0,
                    lan_fcs_ind=0,
                    tp_type=11,
                    tp_pointer=0x401,
                    mac_learning_depth=0
                )
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)
        frame2 = OmciFrame(hex2raw(ref))
        self.assertEqual(frame2, frame)

    def test_mib_upload(self):
        ref = b'00304D0A000200000000000000000000' \
              b'00000000000000000000000000000000' \
              b'000000000000000000000028'
        frame = OmciFrame(
            transaction_id=48,
            message_type=OmciMibUpload.message_id,
            omci_message=OmciMibUpload(
                entity_class=OntData.class_id
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_parse_enh_security_avc(self):
        refs = [
            b"0000110a014c0000008000202020202020202020202020202020202020202020"
            b"2020202020202020000000280be43cf4"
        ]
        for i, data in enumerate(refs):
            frame = OmciFrame(hex2raw(data))
            omci = frame.omci_message
            # frame.show()

    def test_parse_alarm_message(self):
        refs = [
            b"0000100a00050101000000000000000000000000000000000000000000000000"
            b"0000000220000000000000280be43cf4"
        ]
        for i, data in enumerate(refs):
            frame = OmciFrame(hex2raw(data))
            omci = frame.omci_message
            # frame.show()

    def test_parse_results(self):
        refs = [
            b"00001B0a014c0000008000202020202020202020202020202020202020202020"
            b"2020202020202020000000280be43cf4"
        ]
        for i, data in enumerate(refs):
            frame = OmciFrame(hex2raw(data))
            omci = frame.omci_message
            # frame.show()

    def test_parsing_mib_upload_next_responses(self):
        refs = [
            b"00032e0a00020000000200008000000000000000000000000000000000000000"
            b"00000000000000000000002828ce00e2",
            b"00042e0a0002000000050101f0002f2f05202020202020202020202020202020"
            b"202020202000000000000028d4eb4bdf",
            b"00052e0a00020000000501010f80202020202020202020202020202020202020"
            b"2020000000000000000000282dbe4b44",
            b"00062e0a0002000000050104f000303001202020202020202020202020202020"
            b"202020202000000000000028ef1b035b",
            b"00072e0a00020000000501040f80202020202020202020202020202020202020"
            b"202000000000000000000028fec29135",
            b"00082e0a0002000000050180f000f8f801202020202020202020202020202020"
            b"202020202000000000000028fd4e0b07",
            b"00092e0a00020000000501800f80202020202020202020202020202020202020"
            b"2020000000000000000000283306b3c0",
            b"000a2e0a0002000000060101f0002f054252434d123456780000000000000000"
            b"00000000000c000000000028585c2083",
            b"000b2e0a00020000000601010f004252434d0000000000000000000000000000"
            b"0000000000000000000000284f0e82b9",
            b"000c2e0a000200000006010100f8202020202020202020202020202020202020"
            b"202000000000000000000028e68bdb63",
            b"000d2e0a00020000000601010004000000000000000000000000000000000000"
            b"00000000000000000000002857bc2730",
            b"000e2e0a0002000000060104f00030014252434d123456780000000000000000"
            b"00000000000c000000000028afe656f5",
            b"000f2e0a00020000000601040f004252434d0000000000000000000000000000"
            b"000000000000000000000028f8f6db74",
            b"00102e0a000200000006010400f8202020202020202020202020202020202020"
            b"202000000800000000000028064fc177",
            b"00112e0a00020000000601040004000000000000000000000000000000000000"
            b"0000000000000000000000285a5c0841",
            b"00122e0a0002000000060180f000f8014252434d123456780000000000000000"
            b"00000000000c0000000000286826eafe",
            b"00132e0a00020000000601800f004252434d0000000000000000000000000000"
            b"0000000000000000000000281c4b7033",
            b"00142e0a000200000006018000f8202020202020202020202020202020202020"
            b"202000084040000000000028ac144eb3",
            b"00152e0a00020000000601800004000000000000000000000000000000000000"
            b"0000000000000000000000280a81a9a7",
            b"00162e0a0002000000070000f0003530323247574f3236363230303301010100"
            b"0000000000000000000000287ea42d51",
            b"00172e0a0002000000070001f0003530323247574f3236363230303300000100"
            b"000000000000000000000028b17f567f",
            b"00182e0a0002000000830000c000202020202020202020202020202020202020"
            b"2020202020200000000000280e7eebaa",
            b"00192e0a00020000008300002000202020202020202020202020202000000000"
            b"000000000000000000000028a95c03b3",
            b"001a2e0a00020000008300001000000000000000000000000000000000000000"
            b"000000000000000000000028f30515a1",
            b"001b2e0a0002000000850000ffe0000000000000000000000000000000000000"
            b"000000000000000000000028764c18de",
            b"001c2e0a0002000000860001c00000001018aaaa000000000000000000000000"
            b"000000000000000000000028ea220ce0",
            b"001d2e0a00020000008600012000000000000000000000000000000000000000"
            b"000000000000000000000028fbdb571a",
            b"001e2e0a00020000008600011f80000000000000000000000000000000000000"
            b"000000000000000000000028c2682282",
            b"001f2e0a00020000008600010078000000000000000000000000000000000000"
            b"0000000000000000000000289c4809b1",
            b"00202e0a00020000008600010004000000000000000000000000000000000000"
            b"000000000000000000000028d174a7d6",
            b"00212e0a00020000008600010002000000000000000000000000000000000000"
            b"0000000000000000000000288f353976",
            b"00222e0a0002000001000000e0004252434d0000000000000000000000000000"
            b"4252434d123456780000002803bbceb6",
            b"00232e0a00020000010000001f80000000000000000000000000000000000000"
            b"0000000000000000000000281b9674db",
            b"00242e0a00020000010000000040000000000000000000000000000000000000"
            b"000000000000000000000028b1050b9b",
            b"00252e0a00020000010000000038000000000000000000000000000003000000"
            b"0000000000000000000000288266645e",
            b"00262e0a0002000001010000f80042564d344b3030425241303931352d303038"
            b"3300b3000001010000000028837d624f",
            b"00272e0a000200000101000007f8000000010020027c85630016000030000000"
            b"00000000000000000000002896c707e1",
            b"00282e0a0002000001068000e00000ff01010000000000000000000000000000"
            b"00000000000000000000002811acb324",
            b"00292e0a0002000001068001e00000ff01010000000000000000000000000000"
            b"00000000000000000000002823ad6aa9",
            b"002a2e0a0002000001068002e00000ff01010000000000000000000000000000"
            b"000000000000000000000028a290efd9",
            b"002b2e0a0002000001068003e00000ff01010000000000000000000000000000"
            b"000000000000000000000028af893357",
            b"002c2e0a0002000001068004e00000ff01010000000000000000000000000000"
            b"000000000000000000000028901141a3",
            b"002d2e0a0002000001068005e00000ff01010000000000000000000000000000"
            b"000000000000000000000028c4398bcc",
            b"002e2e0a0002000001068006e00000ff01010000000000000000000000000000"
            b"000000000000000000000028e60acd99",
            b"002f2e0a0002000001068007e00000ff01010000000000000000000000000000"
            b"0000000000000000000000284b5faf23",
            b"00302e0a0002000001078001ffff01000800300000050900000000ffff000000"
            b"008181000000000000000028bef89455",
            b"00312e0a0002000001080401f000000000000401000000000000000000000000"
            b"0000000000000000000000287dc5183d",
            b"00322e0a0002000001150401fff0000080008000000000040100000000010000"
            b"000000000000000000000028cc0a46a9",
            b"00332e0a0002000001150401000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000288c42acdd",
            b"00342e0a0002000001150402fff0000080008000000000040100010000010000"
            b"000000000000000000000028de9f625a",
            b"00352e0a0002000001150402000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000280587860b",
            b"00362e0a0002000001150403fff0000080008000000000040100020000010000"
            b"000000000000000000000028a49cc820",
            b"00372e0a0002000001150403000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028b4e4a2b9",
            b"00382e0a0002000001150404fff0000080008000000000040100030000010000"
            b"0000000000000000000000288233147b",
            b"00392e0a0002000001150404000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002881b706b0",
            b"003a2e0a0002000001150405fff0000080008000000000040100040000010000"
            b"000000000000000000000028be8efc9f",
            b"003b2e0a0002000001150405000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028d944804b",
            b"003c2e0a0002000001150406fff0000080008000000000040100050000010000"
            b"000000000000000000000028725c3864",
            b"003d2e0a0002000001150406000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000284e2d5cd2",
            b"003e2e0a0002000001150407fff0000080008000000000040100060000010000"
            b"000000000000000000000028464b03ba",
            b"003f2e0a0002000001150407000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000287006cfd0",
            b"00402e0a0002000001150408fff0000080008000000000040100070000010000"
            b"000000000000000000000028cd88ebeb",
            b"00412e0a0002000001150408000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000285a5905e2",
            b"00422e0a0002000001158000fff0000100010000000000800000000000010000"
            b"000000000000000000000028e61b19d1",
            b"00432e0a0002000001158000000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028b0cc5937",
            b"00442e0a0002000001158001fff0000100010000000000800000010000010000"
            b"0000000000000000000000285386bbf2",
            b"00452e0a0002000001158001000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028c06723ab",
            b"00462e0a0002000001158002fff0000100010000000000800000020000010000"
            b"000000000000000000000028ab49704a",
            b"00472e0a0002000001158002000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002857432f25",
            b"00482e0a0002000001158003fff0000100010000000000800000030000010000"
            b"000000000000000000000028b383c057",
            b"00492e0a0002000001158003000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028dca40d66",
            b"004a2e0a0002000001158004fff0000100010000000000800000040000010000"
            b"0000000000000000000000286b7ba0e2",
            b"004b2e0a0002000001158004000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028fd442363",
            b"004c2e0a0002000001158005fff0000100010000000000800000050000010000"
            b"0000000000000000000000280ee9a0b8",
            b"004d2e0a0002000001158005000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028bc1b9843",
            b"004e2e0a0002000001158006fff0000100010000000000800000060000010000"
            b"0000000000000000000000280c535114",
            b"004f2e0a0002000001158006000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002887032f2b",
            b"00502e0a0002000001158007fff0000100010000000000800000070000010000"
            b"000000000000000000000028a77d7f61",
            b"00512e0a0002000001158007000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002835e9f567",
            b"00522e0a0002000001158008fff0000100010000000000800100000000010000"
            b"000000000000000000000028ff4ca94b",
            b"00532e0a0002000001158008000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000281e2f1e33",
            b"00542e0a0002000001158009fff0000100010000000000800100010000010000"
            b"0000000000000000000000283c473db0",
            b"00552e0a0002000001158009000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002869f51dda",
            b"00562e0a000200000115800afff0000100010000000000800100020000010000"
            b"000000000000000000000028046b8feb",
            b"00572e0a000200000115800a000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002868b1495e",
            b"00582e0a000200000115800bfff0000100010000000000800100030000010000"
            b"0000000000000000000000282b927566",
            b"00592e0a000200000115800b000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028cd43de96",
            b"005a2e0a000200000115800cfff0000100010000000000800100040000010000"
            b"000000000000000000000028c49617dd",
            b"005b2e0a000200000115800c000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028fbbb972a",
            b"005c2e0a000200000115800dfff0000100010000000000800100050000010000"
            b"00000000000000000000002893d4c2b5",
            b"005d2e0a000200000115800d000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028dc9d97ca",
            b"005e2e0a000200000115800efff0000100010000000000800100060000010000"
            b"0000000000000000000000280e1ec245",
            b"005f2e0a000200000115800e000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028be3d56f1",
            b"00602e0a000200000115800ffff0000100010000000000800100070000010000"
            b"0000000000000000000000280c046099",
            b"00612e0a000200000115800f000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028d770e4ea",
            b"00622e0a0002000001158010fff0000100010000000000800200000000010000"
            b"0000000000000000000000281b449092",
            b"00632e0a0002000001158010000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000282b7a8604",
            b"00642e0a0002000001158011fff0000100010000000000800200010000010000"
            b"000000000000000000000028ad498068",
            b"00652e0a0002000001158011000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028a114b304",
            b"00662e0a0002000001158012fff0000100010000000000800200020000010000"
            b"000000000000000000000028c091715d",
            b"00672e0a0002000001158012000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028d4ab49e7",
            b"00682e0a0002000001158013fff0000100010000000000800200030000010000"
            b"000000000000000000000028e39dd5dd",
            b"00692e0a0002000001158013000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000288779ebf0",
            b"006a2e0a0002000001158014fff0000100010000000000800200040000010000"
            b"000000000000000000000028c47a741f",
            b"006b2e0a0002000001158014000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028ce765fcd",
            b"006c2e0a0002000001158015fff0000100010000000000800200050000010000"
            b"0000000000000000000000288f732591",
            b"006d2e0a0002000001158015000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028920b6f5e",
            b"006e2e0a0002000001158016fff0000100010000000000800200060000010000"
            b"000000000000000000000028f072e1c3",
            b"006f2e0a0002000001158016000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028b47ea00f",
            b"00702e0a0002000001158017fff0000100010000000000800200070000010000"
            b"00000000000000000000002813461627",
            b"00712e0a0002000001158017000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002809013378",
            b"00722e0a0002000001158018fff0000100010000000000800300000000010000"
            b"0000000000000000000000286168e200",
            b"00732e0a0002000001158018000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028eccc81f7",
            b"00742e0a0002000001158019fff0000100010000000000800300010000010000"
            b"00000000000000000000002855fe8072",
            b"00752e0a0002000001158019000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028c159c496",
            b"00762e0a000200000115801afff0000100010000000000800300020000010000"
            b"00000000000000000000002872652aca",
            b"00772e0a000200000115801a000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000283ba1c255",
            b"00782e0a000200000115801bfff0000100010000000000800300030000010000"
            b"0000000000000000000000286b2ecb95",
            b"00792e0a000200000115801b000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028441fbe05",
            b"007a2e0a000200000115801cfff0000100010000000000800300040000010000"
            b"000000000000000000000028f07ad5d8",
            b"007b2e0a000200000115801c000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028237d6a28",
            b"007c2e0a000200000115801dfff0000100010000000000800300050000010000"
            b"000000000000000000000028e47dfdca",
            b"007d2e0a000200000115801d000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000280ca941be",
            b"007e2e0a000200000115801efff0000100010000000000800300060000010000"
            b"0000000000000000000000283a1ef4d4",
            b"007f2e0a000200000115801e000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000289c905cd5",
            b"00802e0a000200000115801ffff0000100010000000000800300070000010000"
            b"000000000000000000000028384ae4c6",
            b"00812e0a000200000115801f000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028be87eb55",
            b"00822e0a0002000001158020fff0000100010000000000800400000000010000"
            b"000000000000000000000028f0412282",
            b"00832e0a0002000001158020000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028842ada0c",
            b"00842e0a0002000001158021fff0000100010000000000800400010000010000"
            b"000000000000000000000028a6eed1bc",
            b"00852e0a0002000001158021000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000280f3dd903",
            b"00862e0a0002000001158022fff0000100010000000000800400020000010000"
            b"000000000000000000000028474a0823",
            b"00872e0a0002000001158022000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028e00456b3",
            b"00882e0a0002000001158023fff0000100010000000000800400030000010000"
            b"00000000000000000000002851cbe1a6",
            b"00892e0a0002000001158023000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002869a99563",
            b"008a2e0a0002000001158024fff0000100010000000000800400040000010000"
            b"00000000000000000000002867705534",
            b"008b2e0a0002000001158024000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000286f9570c0",
            b"008c2e0a0002000001158025fff0000100010000000000800400050000010000"
            b"000000000000000000000028450ef70e",
            b"008d2e0a0002000001158025000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002847588afa",
            b"008e2e0a0002000001158026fff0000100010000000000800400060000010000"
            b"000000000000000000000028c8218600",
            b"008f2e0a0002000001158026000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028391a6ba7",
            b"00902e0a0002000001158027fff0000100010000000000800400070000010000"
            b"000000000000000000000028afc0878b",
            b"00912e0a0002000001158027000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002819130d66",
            b"00922e0a0002000001158028fff0000100010000000000800500000000010000"
            b"0000000000000000000000289afa4cf7",
            b"00932e0a0002000001158028000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002873a4e20b",
            b"00942e0a0002000001158029fff0000100010000000000800500010000010000"
            b"000000000000000000000028633debd9",
            b"00952e0a0002000001158029000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000280397eb28",
            b"00962e0a000200000115802afff0000100010000000000800500020000010000"
            b"0000000000000000000000280ed5ee7a",
            b"00972e0a000200000115802a000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028f886ba59",
            b"00982e0a000200000115802bfff0000100010000000000800500030000010000"
            b"00000000000000000000002888ff79b1",
            b"00992e0a000200000115802b000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002846baf278",
            b"009a2e0a000200000115802cfff0000100010000000000800500040000010000"
            b"0000000000000000000000281fd1e68f",
            b"009b2e0a000200000115802c000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028d99760f9",
            b"009c2e0a000200000115802dfff0000100010000000000800500050000010000"
            b"000000000000000000000028557aaf84",
            b"009d2e0a000200000115802d000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028064210fd",
            b"009e2e0a000200000115802efff0000100010000000000800500060000010000"
            b"0000000000000000000000285fd6c061",
            b"009f2e0a000200000115802e000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028299efbb5",
            b"00a02e0a000200000115802ffff0000100010000000000800500070000010000"
            b"00000000000000000000002834f127c4",
            b"00a12e0a000200000115802f000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028edd30591",
            b"00a22e0a0002000001158030fff0000100010000000000800600000000010000"
            b"000000000000000000000028183183f2",
            b"00a32e0a0002000001158030000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028a27e71f6",
            b"00a42e0a0002000001158031fff0000100010000000000800600010000010000"
            b"000000000000000000000028bd64dfc0",
            b"00a52e0a0002000001158031000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002839e2f37e",
            b"00a62e0a0002000001158032fff0000100010000000000800600020000010000"
            b"0000000000000000000000283e72282e",
            b"00a72e0a0002000001158032000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028cef19baa",
            b"00a82e0a0002000001158033fff0000100010000000000800600030000010000"
            b"0000000000000000000000281c1caf44",
            b"00a92e0a0002000001158033000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002814712e27",
            b"00aa2e0a0002000001158034fff0000100010000000000800600040000010000"
            b"000000000000000000000028f02a30a4",
            b"00ab2e0a0002000001158034000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028068fcbf5",
            b"00ac2e0a0002000001158035fff0000100010000000000800600050000010000"
            b"000000000000000000000028436bd783",
            b"00ad2e0a0002000001158035000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000288da3200f",
            b"00ae2e0a0002000001158036fff0000100010000000000800600060000010000"
            b"000000000000000000000028c26a02ca",
            b"00af2e0a0002000001158036000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028147a41ee",
            b"00b02e0a0002000001158037fff0000100010000000000800600070000010000"
            b"0000000000000000000000287c2bbec0",
            b"00b12e0a0002000001158037000f0200020002000200ffff0900000000000000"
            b"0000000000000000000000284c86c11f",
            b"00b22e0a0002000001158038fff0000100010000000000800700000000010000"
            b"00000000000000000000002895b94e06",
            b"00b32e0a0002000001158038000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028a2b34012",
            b"00b42e0a0002000001158039fff0000100010000000000800700010000010000"
            b"00000000000000000000002804b205a3",
            b"00b52e0a0002000001158039000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002886856d76",
            b"00b62e0a000200000115803afff0000100010000000000800700020000010000"
            b"0000000000000000000000282a22752c",
            b"00b72e0a000200000115803a000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028488e67db",
            b"00b82e0a000200000115803bfff0000100010000000000800700030000010000"
            b"000000000000000000000028a55f79ea",
            b"00b92e0a000200000115803b000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002842d77ba7",
            b"00ba2e0a000200000115803cfff0000100010000000000800700040000010000"
            b"000000000000000000000028da65268a",
            b"00bb2e0a000200000115803c000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028c58443ec",
            b"00bc2e0a000200000115803dfff0000100010000000000800700050000010000"
            b"000000000000000000000028997aca59",
            b"00bd2e0a000200000115803d000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028a2670b7d",
            b"00be2e0a000200000115803efff0000100010000000000800700060000010000"
            b"00000000000000000000002813e904cb",
            b"00bf2e0a000200000115803e000f0200020002000200ffff0900000000000000"
            b"000000000000000000000028c387a9e5",
            b"00c02e0a000200000115803ffff0000100010000000000800700070000010000"
            b"000000000000000000000028d556a6b2",
            b"00c12e0a000200000115803f000f0200020002000200ffff0900000000000000"
            b"00000000000000000000002868d9961a",
            b"00c22e0a0002000001168000f000800000000200000000000000000000000000"
            b"000000000000000000000028b69b53c1",
            b"00c32e0a0002000001168001f000800000000200000000000000000000000000"
            b"000000000000000000000028537705d4",
            b"00c42e0a0002000001168002f000800000000200000000000000000000000000"
            b"000000000000000000000028db171b7b",
            b"00c52e0a0002000001168003f000800000000200000000000000000000000000"
            b"000000000000000000000028f9b3fa54",
            b"00c62e0a0002000001168004f000800000000200000000000000000000000000"
            b"000000000000000000000028cdacda4e",
            b"00c72e0a0002000001168005f000800000000200000000000000000000000000"
            b"00000000000000000000002837133b6e",
            b"00c82e0a0002000001168006f000800000000200000000000000000000000000"
            b"000000000000000000000028d6447905",
            b"00c92e0a0002000001168007f000800000000200000000000000000000000000"
            b"000000000000000000000028021a3910",
            b"00ca2e0a0002000001168008f000800100000200000000000000000000000000"
            b"00000000000000000000002835d3cf43",
            b"00cb2e0a0002000001168009f000800100000200000000000000000000000000"
            b"00000000000000000000002887ad76fc",
            b"00cc2e0a000200000116800af000800100000200000000000000000000000000"
            b"00000000000000000000002895e3d838",
            b"00cd2e0a000200000116800bf000800100000200000000000000000000000000"
            b"000000000000000000000028a07489ac",
            b"00ce2e0a000200000116800cf000800100000200000000000000000000000000"
            b"0000000000000000000000285d08821d",
            b"00cf2e0a000200000116800df000800100000200000000000000000000000000"
            b"000000000000000000000028302249a4",
            b"00d02e0a000200000116800ef000800100000200000000000000000000000000"
            b"0000000000000000000000283966d3bc",
            b"00d12e0a000200000116800ff000800100000200000000000000000000000000"
            b"0000000000000000000000289519cdb5",
            b"00d22e0a0002000001168010f000800200000200000000000000000000000000"
            b"0000000000000000000000281bc99b7b",
            b"00d32e0a0002000001168011f000800200000200000000000000000000000000"
            b"000000000000000000000028e483b1a0",
            b"00d42e0a0002000001168012f000800200000200000000000000000000000000"
            b"0000000000000000000000286885d8bd",
            b"00d52e0a0002000001168013f000800200000200000000000000000000000000"
            b"000000000000000000000028cbe7afd8",
            b"00d62e0a0002000001168014f000800200000200000000000000000000000000"
            b"00000000000000000000002809009846",
            b"00d72e0a0002000001168015f000800200000200000000000000000000000000"
            b"0000000000000000000000285bee86c4",
            b"00d82e0a0002000001168016f000800200000200000000000000000000000000"
            b"0000000000000000000000281f25725c",
            b"00d92e0a0002000001168017f000800200000200000000000000000000000000"
            b"00000000000000000000002872e94fe1",
            b"00da2e0a0002000001168018f000800300000200000000000000000000000000"
            b"000000000000000000000028e39d572f",
            b"00db2e0a0002000001168019f000800300000200000000000000000000000000"
            b"0000000000000000000000281c9dcadd",
            b"00dc2e0a000200000116801af000800300000200000000000000000000000000"
            b"0000000000000000000000287c5b8405",
            b"00dd2e0a000200000116801bf000800300000200000000000000000000000000"
            b"00000000000000000000002826334420",
            b"00de2e0a000200000116801cf000800300000200000000000000000000000000"
            b"00000000000000000000002871ee1536",
            b"00df2e0a000200000116801df000800300000200000000000000000000000000"
            b"0000000000000000000000289dfeeeb9",
            b"00e02e0a000200000116801ef000800300000200000000000000000000000000"
            b"000000000000000000000028954d55b3",
            b"00e12e0a000200000116801ff000800300000200000000000000000000000000"
            b"000000000000000000000028930c564e",
            b"00e22e0a0002000001168020f000800400000200000000000000000000000000"
            b"000000000000000000000028b9cec3bf",
            b"00e32e0a0002000001168021f000800400000200000000000000000000000000"
            b"0000000000000000000000284263f268",
            b"00e42e0a0002000001168022f000800400000200000000000000000000000000"
            b"000000000000000000000028913e5219",
            b"00e52e0a0002000001168023f000800400000200000000000000000000000000"
            b"000000000000000000000028efe86fe1",
            b"00e62e0a0002000001168024f000800400000200000000000000000000000000"
            b"000000000000000000000028deb045df",
            b"00e72e0a0002000001168025f000800400000200000000000000000000000000"
            b"000000000000000000000028255bcd32",
            b"00e82e0a0002000001168026f000800400000200000000000000000000000000"
            b"000000000000000000000028355392ad",
            b"00e92e0a0002000001168027f000800400000200000000000000000000000000"
            b"000000000000000000000028404a6aca",
            b"00ea2e0a0002000001168028f000800500000200000000000000000000000000"
            b"0000000000000000000000281de78f94",
            b"00eb2e0a0002000001168029f000800500000200000000000000000000000000"
            b"000000000000000000000028501a3aae",
            b"00ec2e0a000200000116802af000800500000200000000000000000000000000"
            b"0000000000000000000000282947d976",
            b"00ed2e0a000200000116802bf000800500000200000000000000000000000000"
            b"000000000000000000000028095cfe0d",
            b"00ee2e0a000200000116802cf000800500000200000000000000000000000000"
            b"000000000000000000000028bbcfc27a",
            b"00ef2e0a000200000116802df000800500000200000000000000000000000000"
            b"000000000000000000000028dbb27396",
            b"00f02e0a000200000116802ef000800500000200000000000000000000000000"
            b"000000000000000000000028dbe9b225",
            b"00f12e0a000200000116802ff000800500000200000000000000000000000000"
            b"000000000000000000000028840c0b08",
            b"00f22e0a0002000001168030f000800600000200000000000000000000000000"
            b"0000000000000000000000287683e4f8",
            b"00f32e0a0002000001168031f000800600000200000000000000000000000000"
            b"00000000000000000000002844d131d1",
            b"00f42e0a0002000001168032f000800600000200000000000000000000000000"
            b"0000000000000000000000284d2c2c6d",
            b"00f52e0a0002000001168033f000800600000200000000000000000000000000"
            b"000000000000000000000028e89a166c",
            b"00f62e0a0002000001168034f000800600000200000000000000000000000000"
            b"0000000000000000000000280f47db8c",
            b"00f72e0a0002000001168035f000800600000200000000000000000000000000"
            b"0000000000000000000000283ede8b3e",
            b"00f82e0a0002000001168036f000800600000200000000000000000000000000"
            b"000000000000000000000028580547db",
            b"00f92e0a0002000001168037f000800600000200000000000000000000000000"
            b"000000000000000000000028d72a270e",
            b"00fa2e0a0002000001168038f000800700000200000000000000000000000000"
            b"000000000000000000000028c25ce712",
            b"00fb2e0a0002000001168039f000800700000200000000000000000000000000"
            b"000000000000000000000028b908637e",
            b"00fc2e0a000200000116803af000800700000200000000000000000000000000"
            b"0000000000000000000000285b66e6fa",
            b"00fd2e0a000200000116803bf000800700000200000000000000000000000000"
            b"00000000000000000000002855c10393",
            b"00fe2e0a000200000116803cf000800700000200000000000000000000000000"
            b"0000000000000000000000283e94c57d",
            b"00ff2e0a000200000116803df000800700000200000000000000000000000000"
            b"0000000000000000000000284347e7f0",
            b"01002e0a000200000116803ef000800700000200000000000000000000000000"
            b"000000000000000000000028be66429d",
            b"01012e0a000200000116803ff000800700000200000000000000000000000000"
            b"0000000000000000000000284f7db145",
            b"01022e0a0002000001490401c000000000000000000000000000000000000000"
            b"000000000000000000000028470aa043",
            b"01032e0a00020000014904012000000000000000000000000000000000000000"
            b"000000000000000000000028a6bc6e48",
            b"01042e0a00020000014904011800ffffffff0000000000000000000000000000"
            b"000000000000000000000028f747c739",
        ]
        mask = "%5s %9s %20s %9s %s"
        print()
        print(mask % ("seq", "class_id", "class", "instance", "attributes"))
        for i, data in enumerate(refs):
            frame = OmciFrame(hex2raw(data))
            omci = frame.omci_message
            # frame.show()
            print(mask % (
                str(i),
                str(omci.object_entity_class),
                entity_id_to_class_map[omci.object_entity_class].__name__,
                b'0x%x' % omci.object_entity_id,
                '\n                                               '.join(
                    '%s: %s' % (k, v) for k, v in omci.object_data.items())
            ))

    def test_onu_reboot(self):
        ref = b'0016590a01000000000000000000000000000'\
              b'0000000000000000000000000000000000000'\
              b'00000000000028'

        frame = OmciFrame(
            transaction_id=22,
            message_type=OmciReboot.message_id,
            omci_message=OmciReboot(
                entity_class=OntG.class_id,
                entity_id=0
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_omci_entity_ids(self):
        from pyvoltha.adapters.extensions.omci.omci_entities import entity_classes

        # For Entity Classes that have a Managed Entity ID with Set-By-Create
        # access, verify that the attribute name matches 'managed_entity_id'
        #
        # This is critical for the MIB Synchronizer state machine as it needs
        # to backfill Set-By-Create attributes when it sees a Create response
        # but it needs to ignore the 'managed_entity_id' attribute (by name).

        for entity in entity_classes:
            mei_attr = entity.attributes[0]
            self.assertIsNotNone(mei_attr)
            self.assertTrue(AA.SBC not in mei_attr.access or
                            mei_attr.field.name == 'managed_entity_id')

    def test_get_response_without_error_but_too_big(self):
        # This test is related to a bug that I believe is in the BroadCom
        # ONU stack software, or at least it was seen on both an Alpha and
        # an T&W BCM-based onu.  The IEEE 802.1p Mapper Service Profile ME
        # (#130) sent by the ONUs have a payload of 27 octets based on the
        # Attribute Mask in the encoding.  However, get-response baseline
        # messages have the last 4 octets reserved for failed/errored attribute
        # masks so only 25 octets should be allowed.  Of course the 4 octets
        # are only valid if the status code == 9, but they still should
        # be reserved.
        #
        # This test verifies that we can still parse the 27 octet payload
        # since the first rule of interoperability is to be lenient with
        # what you receive and strict with what you transmit.
        #
        ref = b'017d290a008280020000780000000000000000000000' +\
              b'0000000000000000000000000000' +\
              b'01' +\
              b'02' +\
              b'0000' +\
              b'00000028'
        zeros_24 = b'000000000000000000000000000000000000000000000000'
        bytes_24 = unhexlify(zeros_24)
        attributes = {
            "unmarked_frame_option": 0,         # 1 octet
            "dscp_to_p_bit_mapping": bytes_24,  # 24 octets
            "default_p_bit_marking": 1,         # 1 octet   - This is too much
            "tp_type": 2,                       # 1 octet
        }
        frame = OmciFrame(
            transaction_id=0x017d,
            message_type=OmciGetResponse.message_id,
            omci_message=OmciGetResponse(
                entity_class=Ieee8021pMapperServiceProfile.class_id,
                success_code=0,
                entity_id=0x8002,
                attributes_mask=Ieee8021pMapperServiceProfile.mask_for(*list(attributes.keys())),
                data=attributes
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_get_response_with_errors_max_data(self):
        # First a frame with maximum data used up. This aligns the fields up perfectly
        # with the simplest definition of a Get Response
        ref = b'017d290a008280020900600000000000000000000000' +\
              b'0000000000000000000000000000' +\
              b'0010' +\
              b'0008' +\
              b'00000028'
        zeros_24 = b'000000000000000000000000000000000000000000000000'
        bytes_24 = unhexlify(zeros_24)
        good_attributes = {
            "unmarked_frame_option": 0,         # 1 octet
            "dscp_to_p_bit_mapping": bytes_24,  # 24 octets
        }
        unsupported_attributes = ["default_p_bit_marking"]
        failed_attributes_mask = ["tp_type"]

        the_class = Ieee8021pMapperServiceProfile
        frame = OmciFrame(
            transaction_id=0x017d,
            message_type=OmciGetResponse.message_id,
            omci_message=OmciGetResponse(
                entity_class=the_class.class_id,
                success_code=9,
                entity_id=0x8002,
                attributes_mask=the_class.mask_for(*list(good_attributes.keys())),
                unsupported_attributes_mask=the_class.mask_for(*unsupported_attributes),
                failed_attributes_mask=the_class.mask_for(*failed_attributes_mask),
                data=good_attributes
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

    def test_get_response_with_errors_min_data(self):
        # Next a frame with only a little data used up. This aligns will require
        # the encoder and decoder to skip to the last 8 octets of the data field
        # and encode the failed masks there
        ref = b'017d290a00828002090040' +\
              b'01' + b'00000000000000000000' +\
              b'0000000000000000000000000000' +\
              b'0010' +\
              b'0028' +\
              b'00000028'

        good_attributes = {
            "unmarked_frame_option": 1,         # 1 octet
        }
        unsupported_attributes = ["default_p_bit_marking"]
        failed_attributes_mask = ["dscp_to_p_bit_mapping", "tp_type"]

        the_class = Ieee8021pMapperServiceProfile
        frame = OmciFrame(
            transaction_id=0x017d,
            message_type=OmciGetResponse.message_id,
            omci_message=OmciGetResponse(
                entity_class=the_class.class_id,
                success_code=9,
                entity_id=0x8002,
                attributes_mask=the_class.mask_for(*list(good_attributes.keys())),
                unsupported_attributes_mask=the_class.mask_for(*unsupported_attributes),
                failed_attributes_mask=the_class.mask_for(*failed_attributes_mask),
                data=good_attributes
            )
        )
        self.assertGeneratedFrameEquals(frame, ref)

        # Now test decode of the packet
        decoded = OmciFrame(unhexlify(ref))

        orig_fields = frame.fields['omci_message'].fields
        omci_fields = decoded.fields['omci_message'].fields

        for field in ['entity_class', 'entity_id', 'attributes_mask',
                      'success_code', 'unsupported_attributes_mask',
                      'failed_attributes_mask']:
            self.assertEqual(omci_fields[field], orig_fields[field])

        self.assertEqual(omci_fields['data']['unmarked_frame_option'],
                         orig_fields['data']['unmarked_frame_option'])


if __name__ == '__main__':
    main()
