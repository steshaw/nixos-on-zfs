from pybootstrap import prepare

blk_devs = prepare.get_block_devices()
print(blk_devs)
disks_by_id = prepare.get_disks_by_id()
print(disks_by_id)
blk_devs_with_ids = prepare.add_id_to_block_devices(blk_devs, disks_by_id)
print(blk_devs_with_ids)
