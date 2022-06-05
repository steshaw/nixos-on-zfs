from pybootstrap import prepare
import json

def pp(a): return json.dumps(a, indent='  ')
def d(xs): return [x.__dict__ for x in xs]

blk_devs = prepare.get_block_devices()
print("d", d(blk_devs))
print("blk_devs", pp(d(blk_devs)))
disks_by_id = prepare.get_disks_by_path(blk_devs)
#print("disks_by_id", pp(d(disks_by_id)))
blk_devs_with_ids = prepare.add_id_to_block_devices(blk_devs, disks_by_id)
print("blk_devs_with_ids", pp(d(blk_devs_with_ids)))

print("--------------------------------------------------------")
blk_devs = prepare.get_block_devices()
print("blk_devs", blk_devs)
disks_by_id = prepare.get_disks_by_path(blk_devs)
print("XXX")
print("disks_by_id", disks_by_id)
blk_devs = prepare.add_id_to_block_devices(blk_devs, disks_by_id)
print("blk_devs (with ids)", blk_devs)
