'''A module for partitioning for zpool and zfs dataset creation.'''
from pathlib import Path
import subprocess
from typing import NamedTuple

import questionary

from pybootstrap.prepare import ZfsSystemConfig
from pybootstrap.zfs import ZDataset, ZPool, ZPoolProps, ZfsProps

def r(args):
    print("Running", args)
    return subprocess.run(args, check=True)

class SGDisk(NamedTuple):
    partnum: int
    start: int | str
    end: int | str
    hexcode: str
    alignment: int = None

    def __str__(self) -> str:
        a_flag = '' if self.alignment is None else f'-a {self.alignment}'
        if isinstance(self.end, int):
            n_flag_end = 0 if self.end == 0 else f'+{self.end}G'
        elif isinstance(self.end, str):
            n_flag_end = 0 if self.end == '' else self.end
        n_flag = f'-n {self.partnum}:{self.start}:{n_flag_end}'
        t_flag = f'-t {self.partnum}:{self.hexcode}'
        return ' '.join(('sgdisk', a_flag, n_flag, t_flag))


def partition(config: ZfsSystemConfig):
    wipe_disks(config=config)
    sgdisk(config=config)
    zfs_create(config=config)


def wipe_disks(config: ZfsSystemConfig) -> None:
    response = questionary.confirm(
        message='Wipe solid-state drives (recommended)?',
        auto_enter=False
    )
    if response:
        for disk in config.zfs.disks:
            r(f'blkdiscard -f {disk}'.split())


def sgdisk(config: ZfsSystemConfig) -> None:
    commands = []

    zap = 'sgdisk --zap-all'
    commands.append(zap)

    esp_part = SGDisk(partnum=1,
                      start='1M',
                      end=int(config.part.esp),
                      hexcode='EF00')
    commands.append(esp_part)

    boot_part = SGDisk(partnum=2,
                       start=0,
                       end=int(config.part.boot),
                       hexcode='BE00')
    commands.append(boot_part)

    if config.part.swap not in ('', 0):
        swap_part = SGDisk(partnum=4,
                           start=0,
                           end=int(config.part.swap),
                           hexcode=8200)
        commands.append(swap_part)

    if config.part.root in (0, ''):
        root_part = SGDisk(partnum=3,
                           start=0,
                           end=0,
                           hexcode='BF00')
    else:
        root_part = SGDisk(partnum=3,
                           start=0,
                           end=config.part.root,
                           hexcode='BF00')
    commands.append(root_part)

    legacy_part = SGDisk(partnum=5,
                         start='24k',
                         end='+1000K',
                         hexcode='EF02',
                         alignment=1)
    commands.append(legacy_part)

    for disk in config.zfs.disks:
        for cmd in commands:
            cmd_str = ' '.join((str(cmd), disk))
            r(cmd_str.split())
            # print(' '.join((str(cmd), disk)))
    r('sync')
    r('sleep 3'.split())


def zfs_create(config: ZfsSystemConfig):
    # Create the boot pool
    bpool_zpoolprops = ZPoolProps(
        altroot=Path('/mnt'),
        ashift=13,
        autotrim='on',
        compatibility='grub2'
    )
    bpool_zfsprops = ZfsProps(
        prefix='O',
        atime='on',
        acltype='posixacl',
        canmount='off',
        compression='lz4',
        devices='off',
        normalization='formD',
        relatime='on',
        xattr='sa',
        mountpoint=Path('/boot')
    )

    bpool_name = 'bpool_' + config.zfs.pool_uuid
    bpool_parts = [f'{disk}2' for disk in config.zfs.disks]
    bpool_vdev_type = ''
    if len(config.zfs.disks) > 1:
        bpool_vdev_type = 'mirror'

    bpool = ZPool(zpoolprops=bpool_zpoolprops, zfsprops=bpool_zfsprops)
    bpool_create = bpool.create(name=bpool_name,
                                disks=bpool_parts,
                                vdev_type=bpool_vdev_type)
    r(bpool_create.split())

    # Create the root pool
    rpool_zpoolprops = ZPoolProps(
        altroot=Path('/mnt'),
        ashift=13,
        autotrim='on',
        compatibility='off'
    )

    rpool_zfsprops = ZfsProps(
        prefix='O',
        atime='on',
        acltype='posixacl',
        canmount='off',
        compression='zstd',
        dnodesize='auto',
        encryption='aes-256-gcm',
        keylocation='prompt',
        keyformat='passphrase',
        normalization='formD',
        relatime='on',
        xattr='sa',
        mountpoint=Path('/')
    )

    rpool_name = 'rpool_' + config.zfs.pool_uuid
    rpool_parts = [f'{disk}3' for disk in config.zfs.disks]
    rpool_vdev_type = config.zfs.topology

    rpool = ZPool(zpoolprops=rpool_zpoolprops, zfsprops=rpool_zfsprops)
    rpool_create = rpool.create(name=rpool_name,
                                disks=rpool_parts,
                                vdev_type=rpool_vdev_type)
    r(rpool_create.split())

    # Create OS dataset
    root_os_zfsprops = ZfsProps(
        prefix='o',
        canmount='off',
        encryption='aes-256-gcm',
        keylocation='prompt',
        keyformat='passphrase',
        mountpoint='none'
    )
    root_os_path = Path(rpool_name) / config.zfs.os_id
    root_os_dataset = ZDataset(zfsprops=root_os_zfsprops)
    r(root_os_dataset.create(filesystem=root_os_path).split())

    # Common
    container_props = ZfsProps(prefix='o', canmount='off', mountpoint='none')

    # Create ROOT datasets
    root_zfsprops = container_props
    root_path = root_os_path / 'ROOT'
    root_dataset = ZDataset(zfsprops=root_zfsprops)
    r(root_dataset.create(filesystem=root_path).split())

    rdefault_zfsprops = ZfsProps(
        prefix='o',
        canmount='noauto',
        mountpoint=Path('/')
    )
    rdefault_path = root_path / 'default'
    rdefault_dataset = ZDataset(zfsprops=rdefault_zfsprops)
    r(rdefault_dataset.create(filesystem=rdefault_path).split())

    r(f'zfs mount {rdefault_path}'.split())

    # Create BOOT datasets
    boot_os_zfsprops = container_props
    boot_os_path = Path(bpool_name) / config.zfs.os_id
    boot_os_dataset = ZDataset(zfsprops=boot_os_zfsprops)
    r(boot_os_dataset.create(filesystem=boot_os_path).split())

    boot_zfsprops = container_props
    boot_path = boot_os_path / 'BOOT'
    boot_dataset = ZDataset(zfsprops=boot_zfsprops)
    r(boot_dataset.create(filesystem=boot_path).split())

    bdefault_zfsprops = ZfsProps(
        prefix='o',
        canmount='noauto',
        mountpoint=Path('/boot')
    )
    bdefault_path = boot_path / 'default'
    bdefault_dataset = ZDataset(zfsprops=bdefault_zfsprops)
    r(bdefault_dataset.create(bdefault_path).split())

    r(f'zfs mount {bdefault_path}'.split())

    # Create DATA datasets
    data_zfsprops = container_props
    data_path = root_os_path / 'DATA'
    data_dataset = ZDataset(zfsprops=data_zfsprops)
    r(data_dataset.create(filesystem=data_path).split())

    # Create datasets for mounting nix specific paths
    dlocal_zfsprops = ZfsProps(
        prefix='o',
        canmount='off',
        mountpoint=Path('/')
    )
    dlocal_path = data_path / 'local'
    dlocal_dataset = ZDataset(zfsprops=dlocal_zfsprops)
    r(dlocal_dataset.create(filesystem=dlocal_path).split())

    for nixdir in ('nix', ):
        nixdir_zfsprops = ZfsProps(prefix='o',
                                   canmount='on',
                                   mountpoint=Path('/') / nixdir)
        nixdir_path = dlocal_path / nixdir
        nixdir_dataset = ZDataset(zfsprops=nixdir_zfsprops)
        r(nixdir_dataset.create(filesystem=nixdir_path).split())

    # Create user/shared/persistent datasets
    data_default_props = ZfsProps( prefix='o', mountpoint=Path('/'), canmount='off')
    data_default_path = data_path / 'default'
    data_default_dataset = ZDataset(zfsprops=data_default_props)
    r(data_default_dataset.create(filesystem=data_default_path).split())

    # containers
    for shared_con in ('usr', 'var', 'var/lib'):
        shared_con_props = ZfsProps(prefix='o', canmount='off')
        shared_con_path = data_default_path / shared_con
        shared_con_dataset = ZDataset(zfsprops=shared_con_props)
        r(shared_con_dataset.create(filesystem=shared_con_path).split())

    # mounted directories
    for shared in ('home', 'root', 'srv', 'usr/local', 'var/log', 'var/spool'):
        shared_props = ZfsProps(prefix='o', canmount='on')
        shared_path = data_default_path / shared
        shared_dataset = ZDataset(zfsprops=shared_props)
        r(shared_dataset.create(filesystem=shared_path).split())

    # chmod root
    r('chmod 750 /mnt/root'.split())

    # Create a state dataset for saving mutable data in case an
    # immutable file system is used
    state_props = ZfsProps(prefix='o', canmount='on')
    state_path = data_default_path / 'state'
    state_dataset = ZDataset(zfsprops=state_props)
    r(state_dataset.create(filesystem=state_path).split())

    mnt_state = Path('/mnt/state')
    mnt = Path('/mnt')
    for state in ('etc/nixos', 'etc/cryptkey.d'):
        r(f'mkdir -p {mnt_state / state} {mnt / state}'.split())
        r(f'mount -o bind {mnt_state / state} {mnt / state}'.split())

    # Create an `empty` dataset to use as an original snapshot for an
    # immutable file system.
    empty_props = ZfsProps(prefix='o', canmount='noauto', mountpoint=Path('/'))
    empty_path = root_path / 'empty'
    empty_dataset = ZDataset(zfsprops=empty_props)
    r(empty_dataset.create(filesystem=empty_path).split())
    r(f'zfs snapshot {empty_path}@start'.split())

    # Format and mount ESP
    for disk in config.zfs.disks:
        r(f'mkfs.vfat -n EFI {disk}1'.split())
        disk_id = Path(disk).stem
        r(f'mkdir -p /mnt/boot/efis/{disk_id}1'.split())
        r(f'mount -t vfat {disk}1 /mnt/boot/efis/{disk_id}1'.split())


if __name__ == '__main__':
    pass
