# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

from __future__ import annotations

import json

from extra_platforms import LINUX_LIKE

from ..base import PackageManager
from ..capabilities import version_not_implemented
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class FWUPD(PackageManager):
    name = "Linux Vendor Firmware Service"

    homepage_url = "https://fwupd.org"

    platforms = LINUX_LIKE

    requirement = "1.9.5"
    """Version `1.9.5 is the first supporting --json parameter for get-devices command
    <https://github.com/fwupd/fwupd/releases/tag/1.9.5>`_.
    """

    cli_names = ("fwupdmgr",)

    pre_args = (
        # Answer yes to all questions.
        "--assume-yes",
        # Do not check or prompt for reboot after update.
        "--no-reboot-check",
        # Do not prompt for devices.
        "--no-device-prompt",
    )

    version_regexes = (r"compile\s+org\.freedesktop\.fwupd\s+(?P<version>\S+)\s+",)
    """
    .. code-block:: shell-session

        $ fwupdmgr --version
        compile   com.hughsie.libxmlb           0.3.18
        compile   com.hughsie.libjcat           0.2.0
        compile   org.freedesktop.fwupd         1.9.24
        runtime   org.freedesktop.fwupd-efi     1.4
        compile   org.freedesktop.gusb          0.4.8
        runtime   com.hughsie.libxmlb           0.3.x
        runtime   org.freedesktop.gusb          0.4.8
        runtime   com.hughsie.libjcat           0.2.0
        runtime   org.freedesktop.fwupd         1.9.24
        runtime   org.kernel                    6.8.0-48-generic
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ fwupdmgr --assume-yes --no-reboot-check --no-device-prompt get-devices --json | jq
            {
              "Devices": [
                {
                  "Name": "USB2.0 Hub",
                  "DeviceId": "7622d5fdbf1d1e08138156da7d83bf693986ad16",
                  "ParentDeviceId" : "b5540761dfe33d9abccd3bb21f1d725f9e69f541",
                  "CompositeId" : "b5540761dfe33d9abccd3bb21f1d725f9e69f541",
                  "InstanceIds": [
                    "USB\\VID_17EF&PID_3080",
                    "USB\\VID_17EF&PID_3080&REV_5163",
                    "USB\\VID_17EF&PID_3080&HUB_20",
                    "USB\\VID_17EF&PID_3080&SPI_C220",
                    "USB\\VID_17EF&PID_3080&SPI_C220&REV_5163",
                    "USB\\VID_17EF&PID_3080&DEV_VL820Q7"
                  ],
                  "Guid": [
                    "8ee94f0e-9b44-596a-bdd9-6f90401664cc",
                    "35199e34-cf82-5b09-9287-622d225056e4",
                    "0987e3c9-b1ee-5763-ac6e-51329b034e4b",
                    "163cea66-5a78-58af-80ba-21be960aae5c",
                    "c7def18d-66ae-5531-924b-2020c3638181"
                  ],
                  "Summary": "USB 3.x hub",
                  "Plugin": "vli",
                  "Protocol" : "com.vli.usbhub",
                  "Flags": [
                    "updatable",
                    "registered",
                    "can-verify",
                    "can-verify-image",
                    "dual-image",
                    "self-recovery",
                    "add-counterpart-guids",
                    "unsigned-payload"
                  ],
                  "Vendor": "VIA Labs, Inc.",
                  "VendorId" : "USB:0x17EF",
                  "Version": "51.63",
                  "VersionFormat" : "bcd",
                  "VersionRaw": 20835,
                  "Icons": [
                    "usb-hub"
                  ],
                  "InstallDuration" : 15,
                  "Created": 1686048073
                },
                {
                  "DeviceId" : "20de1d77d0d1787bc56ef62f7d05de49361e1e07",
                  "InstanceIds" : [
                    "DRM\\VEN_RHT&DEV_1234"
                  ],
                  "Guid" : [
                    "90b1437c-86da-5374-a9a7-ceca8b0afd5e"
                  ],
                  "Plugin" : "linux_display",
                  "Flags" : [
                    "registered"
                  ],
                  "Created" : 1731659840
                },
                {
                  "Name" : "UEFI dbx",
                  "DeviceId" : "362301da643102b9f38477387e2193e57abaa590",
                  "InstanceIds" : [
                    "UEFI\\CRT_E1FFABB40A30D9EE750BDA8BAF36ACA304FF20526138129247576B3339C54537&ARCH_AA64",
                    "UEFI\\CRT_A1117F516A32CEFCBA3F2D1ACE10A87972FD6BBE8FE0D0B996E09E65D802A503&ARCH_AA64"
                  ],
                  "Guid" : [
                    "a9b31b16-b184-560f-97cb-1aa25e418c7d",
                    "67d35028-ca5b-5834-834a-f97380381082"
                  ],
                  "Summary" : "UEFI revocation database",
                  "Plugin" : "uefi_dbx",
                  "Protocol" : "org.uefi.dbx",
                  "Flags" : [
                    "internal",
                    "updatable",
                    "supported",
                    "registered",
                    "needs-reboot",
                    "usable-during-update",
                    "only-version-upgrade",
                    "signed-payload"
                  ],
                  "Checksums" : [
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                  ],
                  "VendorId" : "UEFI:Linux Foundation",
                  "Version" : "0",
                  "VersionLowest" : "0",
                  "VersionFormat" : "number",
                  "Icons" : [
                    "computer"
                  ],
                  "InstallDuration" : 1,
                  "Created" : 1731659840,
                  "Releases" : [
                    {
                      "AppstreamId" : "org.linuxfoundation.dbx.aa64.firmware",
                      "ReleaseId" : "35289",
                      "RemoteId" : "lvfs",
                      "Name" : "Secure Boot dbx",
                      "NameVariantSuffix" : "aa64",
                      "Summary" : "UEFI Secure Boot Forbidden Signature Database",
                      "Description" : "<p>Insecure versions of the Microsoft Windows boot manager affected by Black Lotus were added to the list of forbidden signatures due to a discovered security problem.This updates the dbx to the latest release from Microsoft.</p><p>Before installing the update, fwupd will check for any affected executables in the ESP and will refuse to update if it finds any boot binaries signed with any of the forbidden signatures.Applying this update may also cause some Windows install media to not start correctly.</p>",
                      "Version" : "26",
                      "Filename" : "DBXUpdate-20230509-aa64.cab",
                      "Protocol" : "org.uefi.dbx",
                      "Categories" : [
                        "X-Configuration",
                        "X-System"
                      ],
                      "Issues" : [
                        "CVE-2022-21894"
                      ],
                      "Checksum" : [
                        "46a42362cd34c0d103cf534ca431508d24715e51",
                        "3ff3f17a9e5d372e51503803f22294f32ca90d1fe570b0bef4088c3a542617e6"
                      ],
                      "License" : "LicenseRef-proprietary",
                      "Size" : 4610,
                      "Created" : 1683590400,
                      "Locations" : [
                        "https://fwupd.org/downloads/3ff3f17a9e5d372e51503803f22294f32ca90d1fe570b0bef4088c3a542617e6-DBXUpdate-20230509-aa64.cab"
                      ],
                      "Uri" : "https://fwupd.org/downloads/3ff3f17a9e5d372e51503803f22294f32ca90d1fe570b0bef4088c3a542617e6-DBXUpdate-20230509-aa64.cab",
                      "Homepage" : "https://uefi.org/revocationlistfile",
                      "Vendor" : "Linux Foundation",
                      "Flags" : [
                        "trusted-metadata",
                        "is-upgrade"
                      ],
                      "InstallDuration" : 1
                    },
                    {
                      "AppstreamId" : "org.linuxfoundation.dbx.aa64.firmware",
                      "ReleaseId" : "28503",
                      "RemoteId" : "lvfs",
                      "Name" : "Secure Boot dbx",
                      "NameVariantSuffix" : "aa64",
                      "Summary" : "UEFI Secure Boot Forbidden Signature Database",
                      "Description" : "<p>An insecure version of software from vmware has been added to the list of forbidden signatures due to a discovered security problem.This updates the dbx to the latest release from Microsoft.</p><p>Before installing the update, fwupd will check for any affected executables in the ESP and will refuse to update if it finds any boot binaries signed with any of the forbidden signatures.</p>",
                      "Version" : "22",
                      "Filename" : "DBXUpdate-20230314-aa64.cab",
                      "Protocol" : "org.uefi.dbx",
                      "Categories" : [
                        "X-Configuration",
                        "X-System"
                      ],
                      "Issues" : [
                        "CVE-2023-28005"
                      ],
                      "Checksum" : [
                        "611e745638f05e9a11c2998cfba38f0bad651141",
                        "533ce4ac028585925268d9e39079b71730a7abd94f611bc532707938d4271ad3"
                      ],
                      "License" : "LicenseRef-proprietary",
                      "Size" : 4418,
                      "Created" : 1678752000,
                      "Locations" : [
                        "https://fwupd.org/downloads/533ce4ac028585925268d9e39079b71730a7abd94f611bc532707938d4271ad3-DBXUpdate-20230314-aa64.cab"
                      ],
                      "Uri" : "https://fwupd.org/downloads/533ce4ac028585925268d9e39079b71730a7abd94f611bc532707938d4271ad3-DBXUpdate-20230314-aa64.cab",
                      "Homepage" : "https://uefi.org/revocationlistfile",
                      "Vendor" : "Linux Foundation",
                      "Flags" : [
                        "trusted-metadata",
                        "is-upgrade"
                      ],
                      "InstallDuration" : 1
                    },
                    {
                      "AppstreamId" : "org.linuxfoundation.dbx.aa64.firmware",
                      "ReleaseId" : "15180",
                      "RemoteId" : "lvfs",
                      "Name" : "Secure Boot dbx",
                      "NameVariantSuffix" : "aa64",
                      "Summary" : "UEFI Secure Boot Forbidden Signature Database",
                      "Description" : "<p>This updates the dbx to the latest release from Microsoft which adds insecure versions of grub and shim to the list of forbidden signatures due to multiple discovered security updates.</p>",
                      "Version" : "21",
                      "Filename" : "DBXUpdate-20220812-aa64.cab",
                      "Protocol" : "org.uefi.dbx",
                      "Categories" : [
                        "X-Configuration",
                        "X-System"
                      ],
                      "Issues" : [
                        "CVE-2022-34303",
                        "309662",
                        "CVE-2022-34302",
                        "CVE-2022-34301"
                      ],
                      "Checksum" : [
                        "4032a1d8734e6085f4a6e4bb26a038eb639603b9",
                        "bf56092de6586604d2b41d5bb4c9b7787a07adde408fd4134a3f3606f7fda999"
                      ],
                      "License" : "LicenseRef-proprietary",
                      "Size" : 4370,
                      "Created" : 1595980800,
                      "Locations" : [
                        "https://fwupd.org/downloads/bf56092de6586604d2b41d5bb4c9b7787a07adde408fd4134a3f3606f7fda999-DBXUpdate-20220812-aa64.cab"
                      ],
                      "Uri" : "https://fwupd.org/downloads/bf56092de6586604d2b41d5bb4c9b7787a07adde408fd4134a3f3606f7fda999-DBXUpdate-20220812-aa64.cab",
                      "Homepage" : "https://uefi.org/revocationlistfile",
                      "Vendor" : "Linux Foundation",
                      "Flags" : [
                        "trusted-metadata",
                        "is-upgrade"
                      ],
                      "InstallDuration" : 1
                    }
                  ]
                },
                {
                  "Name" : "Virtio network device",
                  "DeviceId" : "17076870bcf7a84a9c8e999d7e54e39b446032bb",
                  "InstanceIds" : [
                    "PCI\\VEN_1AF4&DEV_1000",
                    "PCI\\VEN_1AF4&DEV_1000&SUBSYS_1AF40001"
                  ],
                  "Guid" : [
                    "21c85fac-5270-576f-a84e-04969f8cf75a",
                    "b93ef629-0df1-5505-9fee-6992b8b9abd8"
                  ],
                  "Plugin" : "optionrom",
                  "Flags" : [
                    "internal",
                    "registered",
                    "can-verify",
                    "can-verify-image"
                  ],
                  "Vendor" : "Red Hat, Inc.",
                  "VendorId" : "PCI:0x1AF4",
                  "Created" : 1731659840
                }
              ]
            }
        """
        output = self.run_cli("get-devices", "--json")

        if output:
            for device in json.loads(output)["Devices"]:
                if "updatable" in device["Flags"]:
                    yield self.package(
                        id=device["DeviceId"],
                        name=device["Name"],
                        installed_version=device["Version"],
                    )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ fwupdmgr --assume-yes --no-reboot-check --no-device-prompt get-updates --json | jq
            {
              "Devices" : [
                {
                  "Name" : "UEFI dbx",
                  "DeviceId" : "362301da643102b9f38477387e2193e57abaa590",
                  "InstanceIds" : [
                    "UEFI\\CRT_E1FFABB40A30D9EE750BDA8BAF36ACA304FF20526138129247576B3339C54537&ARCH_AA64",
                    "UEFI\\CRT_A1117F516A32CEFCBA3F2D1ACE10A87972FD6BBE8FE0D0B996E09E65D802A503&ARCH_AA64"
                  ],
                  "Guid" : [
                    "a9b31b16-b184-560f-97cb-1aa25e418c7d",
                    "67d35028-ca5b-5834-834a-f97380381082"
                  ],
                  "Summary" : "UEFI revocation database",
                  "Plugin" : "uefi_dbx",
                  "Protocol" : "org.uefi.dbx",
                  "Flags" : [
                    "internal",
                    "updatable",
                    "supported",
                    "registered",
                    "needs-reboot",
                    "usable-during-update",
                    "only-version-upgrade",
                    "signed-payload"
                  ],
                  "Checksums" : [
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                  ],
                  "VendorId" : "UEFI:Linux Foundation",
                  "Version" : "0",
                  "VersionLowest" : "0",
                  "VersionFormat" : "number",
                  "Icons" : [
                    "computer"
                  ],
                  "InstallDuration" : 1,
                  "Created" : 1731659840,
                  "Releases" : [
                    {
                      "AppstreamId" : "org.linuxfoundation.dbx.aa64.firmware",
                      "ReleaseId" : "35289",
                      "RemoteId" : "lvfs",
                      "Name" : "Secure Boot dbx",
                      "NameVariantSuffix" : "aa64",
                      "Summary" : "UEFI Secure Boot Forbidden Signature Database",
                      "Description" : "<p>Insecure versions of the Microsoft Windows boot manager affected by Black Lotus were added to the list of forbidden signatures due to a discovered security problem.This updates the dbx to the latest release from Microsoft.</p><p>Before installing the update, fwupd will check for any affected executables in the ESP and will refuse to update if it finds any boot binaries signed with any of the forbidden signatures.Applying this update may also cause some Windows install media to not start correctly.</p>",
                      "Version" : "26",
                      "Filename" : "DBXUpdate-20230509-aa64.cab",
                      "Protocol" : "org.uefi.dbx",
                      "Categories" : [
                        "X-Configuration",
                        "X-System"
                      ],
                      "Issues" : [
                        "CVE-2022-21894"
                      ],
                      "Checksum" : [
                        "46a42362cd34c0d103cf534ca431508d24715e51",
                        "3ff3f17a9e5d372e51503803f22294f32ca90d1fe570b0bef4088c3a542617e6"
                      ],
                      "License" : "LicenseRef-proprietary",
                      "Size" : 4610,
                      "Created" : 1683590400,
                      "Locations" : [
                        "https://fwupd.org/downloads/3ff3f17a9e5d372e51503803f22294f32ca90d1fe570b0bef4088c3a542617e6-DBXUpdate-20230509-aa64.cab"
                      ],
                      "Uri" : "https://fwupd.org/downloads/3ff3f17a9e5d372e51503803f22294f32ca90d1fe570b0bef4088c3a542617e6-DBXUpdate-20230509-aa64.cab",
                      "Homepage" : "https://uefi.org/revocationlistfile",
                      "Vendor" : "Linux Foundation",
                      "Flags" : [
                        "trusted-metadata",
                        "is-upgrade"
                      ],
                      "InstallDuration" : 1
                    },
                    {
                      "AppstreamId" : "org.linuxfoundation.dbx.aa64.firmware",
                      "ReleaseId" : "28503",
                      "RemoteId" : "lvfs",
                      "Name" : "Secure Boot dbx",
                      "NameVariantSuffix" : "aa64",
                      "Summary" : "UEFI Secure Boot Forbidden Signature Database",
                      "Description" : "<p>An insecure version of software from vmware has been added to the list of forbidden signatures due to a discovered security problem.This updates the dbx to the latest release from Microsoft.</p><p>Before installing the update, fwupd will check for any affected executables in the ESP and will refuse to update if it finds any boot binaries signed with any of the forbidden signatures.</p>",
                      "Version" : "22",
                      "Filename" : "DBXUpdate-20230314-aa64.cab",
                      "Protocol" : "org.uefi.dbx",
                      "Categories" : [
                        "X-Configuration",
                        "X-System"
                      ],
                      "Issues" : [
                        "CVE-2023-28005"
                      ],
                      "Checksum" : [
                        "611e745638f05e9a11c2998cfba38f0bad651141",
                        "533ce4ac028585925268d9e39079b71730a7abd94f611bc532707938d4271ad3"
                      ],
                      "License" : "LicenseRef-proprietary",
                      "Size" : 4418,
                      "Created" : 1678752000,
                      "Locations" : [
                        "https://fwupd.org/downloads/533ce4ac028585925268d9e39079b71730a7abd94f611bc532707938d4271ad3-DBXUpdate-20230314-aa64.cab"
                      ],
                      "Uri" : "https://fwupd.org/downloads/533ce4ac028585925268d9e39079b71730a7abd94f611bc532707938d4271ad3-DBXUpdate-20230314-aa64.cab",
                      "Homepage" : "https://uefi.org/revocationlistfile",
                      "Vendor" : "Linux Foundation",
                      "Flags" : [
                        "trusted-metadata",
                        "is-upgrade"
                      ],
                      "InstallDuration" : 1
                    },
                    {
                      "AppstreamId" : "org.linuxfoundation.dbx.aa64.firmware",
                      "ReleaseId" : "15180",
                      "RemoteId" : "lvfs",
                      "Name" : "Secure Boot dbx",
                      "NameVariantSuffix" : "aa64",
                      "Summary" : "UEFI Secure Boot Forbidden Signature Database",
                      "Description" : "<p>This updates the dbx to the latest release from Microsoft which adds insecure versions of grub and shim to the list of forbidden signatures due to multiple discovered security updates.</p>",
                      "Version" : "21",
                      "Filename" : "DBXUpdate-20220812-aa64.cab",
                      "Protocol" : "org.uefi.dbx",
                      "Categories" : [
                        "X-Configuration",
                        "X-System"
                      ],
                      "Issues" : [
                        "CVE-2022-34303",
                        "309662",
                        "CVE-2022-34302",
                        "CVE-2022-34301"
                      ],
                      "Checksum" : [
                        "4032a1d8734e6085f4a6e4bb26a038eb639603b9",
                        "bf56092de6586604d2b41d5bb4c9b7787a07adde408fd4134a3f3606f7fda999"
                      ],
                      "License" : "LicenseRef-proprietary",
                      "Size" : 4370,
                      "Created" : 1595980800,
                      "Locations" : [
                        "https://fwupd.org/downloads/bf56092de6586604d2b41d5bb4c9b7787a07adde408fd4134a3f3606f7fda999-DBXUpdate-20220812-aa64.cab"
                      ],
                      "Uri" : "https://fwupd.org/downloads/bf56092de6586604d2b41d5bb4c9b7787a07adde408fd4134a3f3606f7fda999-DBXUpdate-20220812-aa64.cab",
                      "Homepage" : "https://uefi.org/revocationlistfile",
                      "Vendor" : "Linux Foundation",
                      "Flags" : [
                        "trusted-metadata",
                        "is-upgrade"
                      ],
                      "InstallDuration" : 1
                    }
                  ]
                }
              ]
            }
        """
        output = self.run_cli("get-updates", "--json")

        if output:
            for device in json.loads(output)["Devices"]:
                if "updatable" in device["Flags"] and device.get("Releases"):
                    yield self.package(
                        id=device["DeviceId"],
                        name=device["Name"],
                        latest_version=max(
                            parse_version(rel["Version"])
                            for rel in device.get("Releases")
                        ),
                        installed_version=device["Version"],
                    )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ sudo fwupdmgr  --assume-yes --no-reboot-check --no-device-prompt install 362301da643102b9f38477387e2193e57abaa590
            WARNING: UEFI capsule updates not available or enabled in firmware setup
            See https://github.com/fwupd/fwupd/wiki/PluginFlag:capsules-unsupported for more information.
            0.	Cancel
            1.	26
            2.	22
            3.	21
            Choose release [0-3]: 3
            Scheduling…              [***************************************]
            Successfully installed firmware

            $ sudo fwupdmgr --assume-yes --no-reboot-check --no-device-prompt install 362301da643102b9f38477387e2193e57abaa590 21
            WARNING: UEFI capsule updates not available or enabled in firmware setup
            See https://github.com/fwupd/fwupd/wiki/PluginFlag:capsules-unsupported for more information.
            Scheduling…              [***************************************]
            362301da643102b9f38477387e2193e57abaa590 is already scheduled to be updated
        """
        package_specs = package_id
        if version:
            package_specs += f" {version}"
        return self.run_cli("install", package_specs, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            $ sudo fwupdmgr --assume-yes --no-reboot-check --no-device-prompt update
        """
        return self.build_cli("update", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            $ sudo fwupdmgr --assume-yes --no-reboot-check --no-device-prompt update 362301da643102b9f38477387e2193e57abaa590
            WARNING: UEFI capsule updates not available or enabled in firmware setup
            See https://github.com/fwupd/fwupd/wiki/PluginFlag:capsules-unsupported for more information.
            Scheduling…              [ -                                     ]
            362301da643102b9f38477387e2193e57abaa590 is already scheduled to be updated
        """
        return self.build_cli("update", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            $ fwupdmgr --assume-yes --no-reboot-check --no-device-prompt refresh --force
            Updating lvfs
            Downloading…             [***************************************]
            Successfully downloaded new metadata: 1 local device supported
        """
        self.run_cli("refresh", "--force")
