from proxmoxer import ProxmoxAPI


def set_cloudinit(prox: ProxmoxAPI, node: str, vmid: int, **kwargs) -> None:
    print(f"Setting cloudinit for VMID {vmid} in {node} {kwargs}")
    prox.nodes(node).qemu(vmid).config.set(**kwargs)
    return