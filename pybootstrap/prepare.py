'''A module to prepare the NixOS root on ZFS configuration.'''
import glob
import json
import math
import os
from pathlib import Path
import random
import string
import subprocess
from time import sleep
from typing import List, NamedTuple, Optional, Sequence
from dataclasses import dataclass
import dataclasses

import questionary


class ZfsConfig(NamedTuple):
    '''Information about the ZFS pool topology and disks.'''
    pool_uuid: str
    os_id: str
    disks: List[str]
    primary_disk: str
    topology: str


class PartitionConfig(NamedTuple):
    '''Information about the partition table sizes.'''
    esp: str
    boot: str
    swap: str
    root: str


class NixOSConfig(NamedTuple):
    '''Information about NixOS configuration.'''
    config: str
    hw_old: str
    hw: str
    path: Path
    zfs: str


class ZfsSystemConfig(NamedTuple):
    '''A system configuration to build NixOS root on ZFS.'''
    zfs: ZfsConfig
    part: PartitionConfig
    nixos: NixOSConfig


@dataclass
class BlockDevice:
    '''Information about a block device.'''
    name: str
    kname: str
    path: str
    model: str
    serial: str
    size: str
    type: str
    id: str = ''
    def __hash__(self):
        return hash((self.name, self.kname, self.path, self.model, self.serial, self.size, self.type, self.id))

@dataclass
class DiskById:
    '''Information about disks by ID.'''
    id: str
    path: str


def prepare() -> ZfsSystemConfig:
    '''Queries the user for ZFS topology, disk selection, and
    partitioning information.

    Returns:
        A system configuration object.
    '''
    disks = get_disks()
    primary_disk = disks[0]
    zfs_config = ZfsConfig(
        pool_uuid=random_str(num=6),
        os_id='nixos',
        disks=disks,
        primary_disk=primary_disk,
        topology=get_topology()
    )

    sys_mem_gb = get_system_memory(size='GiB')
    part_config = PartitionConfig(
        esp=get_partition_size(name='ESP', value=2),
        boot=get_partition_size(name='BOOT', value=4),
        swap=get_partition_size(name='SWAP', value=sys_mem_gb),
        root=get_partition_size(name='ROOT')
    )

    nixos_config = NixOSConfig(
        config='configuration.nix',
        hw_old='hardware-configuration.nix',
        hw='hardware-configuration-zfs.nix',
        path=Path('/mnt/etc/nixos'),
        zfs='zfs.nix'
    )

    sys_config = ZfsSystemConfig(zfs=zfs_config,
                                 part=part_config,
                                 nixos=nixos_config)
    return sys_config


def random_str(num: int = 6) -> str:
    '''Returns a random string (lower case alpha characters only).

    Args:
        num: The number of characters to return.

    Returns:
        The random string.
    '''
    hex_digits = string.ascii_lowercase + string.digits
    return ''.join(random.choice(hex_digits) for _ in range(num))


def get_disks() -> List[str]:
    '''Creates a valid list of disks for the user to select and returns
    a list of the selected disks.

    Returns:
        A list of disks by id.
    '''
    blk_devs = get_block_devices()
    print("blk_devs", blk_devs)
    disks_by_id = get_disks_by_path(blk_devs)
    print("disks_by_id", disks_by_id)
    blk_devs = add_id_to_block_devices(blk_devs, disks_by_id)
    print("blk_devs (with ids)", blk_devs)
    selection = ask_for_disk_selection(blk_devs)
    return selection


def ask_for_disk_selection(blk_devs: List[BlockDevice]) -> List[str]:
    '''Queries the user for a selection of disks to add to the zpool.

    Returns:
        A list of disks by id.
    '''
    keys = ('path', 'path', 'size') # XXX Using path for id here...
    formatted_blk_devs = tabulate_block_devices(blk_devs=blk_devs, keys=keys)

    while True:
        response = questionary.checkbox(
            message='Select disks to add to the pool',
            choices=formatted_blk_devs
        ).ask()

        if len(response) == 0:
            no_disk_color = "\033[0;31m"
            print(no_disk_color + 'No disks were selected!')
            sleep(1)
            continue

        selection = [resp.split()[0] for resp in response]

        sel_color = "\033[1;2;36m"
        print(sel_color + 'Selected disks:\n' + '\n'.join(selection))

        verify = questionary.confirm(
            message='Are you satisfied with your selection?',
            auto_enter=False
        ).ask()
        if not verify:
            continue

        break

    return selection


def tabulate_block_devices(
    blk_devs: List[BlockDevice],
    keys: Sequence[str]
) -> List[str]:
    '''Takes a list of block devices and returns a list of strings that
    can be printed as a nicely formatted table.

    Args:
        blk_devs: A list of block devices.

    Returns:
        The formatted list of strings representing the block devices.
    '''
    dev_list = [[getattr(dev, key) for key in keys] for dev in blk_devs]
    min_col_widths = [len(max(col, key=len)) + 3 for col in zip(*dev_list)]
    row_format = ''.join([f'{{:>{width}}}' for width in min_col_widths])
    return [row_format.format(*row) for row in dev_list]


def get_block_devices() -> List[BlockDevice]:
    '''Creates a list of block devices that are disk types.

    Returns:
        A list of block devices.
    '''
    print("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
    # pylint: disable=no-member
    # pylint: disable=protected-access
    fs = [f.name for f in dataclasses.fields(BlockDevice) if f.default]
    print("fs", fs)
    #non_blk_fields = BlockDevice.__dataclass_field_defaults__.keys()
    lsblk_cols = ','.join(fs)
    print("lsblk_cols", lsblk_cols)

    process = subprocess.run(f'lsblk -d --json -o {lsblk_cols}'.split(),
                             capture_output=True,
                             text=True,
                             check=False)
    block_devices = json.loads(process.stdout)['blockdevices']
    block_devices = [BlockDevice(**dev) for dev in block_devices]
    disks_only = list(filter(lambda dev: dev.type == 'disk', block_devices))
    return disks_only


def get_disks_by_path(blk_devs) -> List[DiskById]:
    '''Creates a list of block devices containing their 'by-id' path and
    /dev/ absolute path.

    Returns:
        A list of disks.
    '''
    if True:
        # XXX: Just using paths
        return [DiskById(id=d.path, path=d.path) for d in blk_devs]
    else:
        disks_by_path = glob.glob('/dev/disk/by-path/*')
        sym_links = [os.path.realpath(disk) for disk in disks_by_path]

        disks_with_symlink = [DiskById(id=id, path=path)
                              for id, path in zip(disks_by_path, sym_links)]
        return disks_with_symlink


def add_id_to_block_devices(
    blk_devs: List[BlockDevice],
    disks_by_id: List[DiskById]
) -> List[BlockDevice]:
    '''Matches a list of block devices to a list of disks by id and adds
    the disk 'by-id' path to the matching block device.

    Args:
        blk_devs: A list of block devices.
        disks_by_id: A list of disks containing they 'by-id' symbolic
        path and /dev/ absolute path.

    Returns:
        A new list of block devices.
    '''
    if True:
        def f(d, n):
            d.id = str(n)
            return d
        return [f(d, n) for d, n in zip(blk_devs, range(1,len(blk_devs) + 1))]
    else:
        new_blk_devs = []
        for dev in blk_devs:
            for disk in disks_by_id:
                print("dev.path", dev.path)
                print("disk.id", disk.path)
                if dev.path == disk.path: # XXX
                    dev.id=disk.id
                    new_blk_devs.append(dev) # Use _replace again? Not found with dataclass...
                    continue
        print("new_blk_devs", new_blk_devs)
        return set(new_blk_devs)


def get_topology() -> str:
    '''Queries the user for a zpool topology.

    Returns:
        The zpool topology.
    '''
    response = questionary.select(
        message='Select a vdev topology.',
        choices=[
            'single',
            'mirror',
            'raidz1',
            'raidz2',
            'raidz3'
        ]
    ).ask()

    if response == 'single':
        return ''
    return response


def get_partition_size(name: str, value: Optional[int] = None) -> string:
    '''Queries the user for a partition size.

    Args:
        name: The name of the partition.
        value: The default value of the partition size.

    Returns:
        The user specified value of the partition size.
    '''
    _value = "" if value is None else value
    input_str = f'Set {name} partition size in GiB [{_value}]:'
    response = questionary.text(
        message=input_str,
        default=str(_value)
    ).ask()
    return response


def get_system_memory(size: str = 'GiB') -> int:
    '''Gets the total system memory in *iB (e.g. GiB) rounded up.

    Args:
        size: The unit of measurement in *iB.

    Returns:
        The value of the total system memory in *iB.

    Raises:
        ValueError: If `size` is not a supported value.
    '''
    sys_mem = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')

    match size:
        case 'B':
            divisor = 1
        case 'KiB':
            divisor = 1024 ** 1
        case 'MiB':
            divisor = 1024 ** 2
        case 'GiB':
            divisor = 1024 ** 3
        case 'TiB':
            divisor = 1024 ** 4
        case _:
            raise ValueError('Unknown size: {size}.')

    return math.ceil(sys_mem / divisor)


if __name__ == '__main__':
    print(prepare())
