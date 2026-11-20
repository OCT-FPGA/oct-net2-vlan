"""OCT Alveo U280 with the existing four VLAN links and a host VLAN test pool."""

import geni.portal as portal
import geni.rspec.pg as pg
import geni.rspec.emulab

pc = portal.Context()
request = pc.makeRequestRSpec()

imageList = [
    ("urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD", "Ubuntu 22.04"),
    ("urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU20-64-STD", "Ubuntu 20.04"),
]
workflow = ["Vitis", "Vivado"]
toolVersion = ["2023.2", "2023.1"]

pc.defineParameter(
    "nodes", "List of nodes", portal.ParameterType.STRING, "pc160,pc161",
    longDescription="Comma-separated UMass OCT nodes. The first node uses VLAN 3811, "
    "and the other nodes use VLAN 3812.",
)
pc.defineParameter(
    "testVlanCount", "Number of host test VLANs", portal.ParameterType.INTEGER, 16,
    longDescription="Extra VLAN links between the Linux hosts. CloudLab assigns "
    "their tags at launch. Set to 0 to request just the four baseline links.",
)
pc.defineParameter(
    "workflow", "Workflow", portal.ParameterType.STRING, workflow[0], workflow,
    longDescription="Select Vitis for application acceleration or Vivado for the traditional workflow.",
)
pc.defineParameter(
    "toolVersion", "Tool Version", portal.ParameterType.STRING, toolVersion[0], toolVersion,
)
pc.defineParameter(
    "osImage", "Select Image", portal.ParameterType.IMAGE, imageList[0], imageList,
)
pc.defineParameter(
    "remoteDesktop", "Remote Desktop Access", portal.ParameterType.BOOLEAN, False,
    longDescription="Install GNOME desktop and VNC server.",
)
pc.defineParameter(
    "tempFileSystemSize", "Temporary Filesystem Size", portal.ParameterType.INTEGER, 0,
    advanced=True, longDescription="Temporary disk space per host in GB.",
)
pc.defineParameter(
    "tempFileSystemMax", "Temp Filesystem Max Space", portal.ParameterType.BOOLEAN, False,
    advanced=True, longDescription="Allocate all available temporary disk space.",
)
pc.defineParameter(
    "tempFileSystemMount", "Temporary Filesystem Mount Point",
    portal.ParameterType.STRING, "/mydata", advanced=True,
)

params = pc.bindParameters()
nodeList = [node.strip() for node in params.nodes.split(",")]
if len(nodeList) < 2 or "" in nodeList or len(set(nodeList)) != len(nodeList):
    pc.reportError(portal.ParameterError(
        "Enter at least two distinct UMass node names separated by commas.", ["nodes"]
    ))
if params.testVlanCount < 0:
    pc.reportError(portal.ParameterError(
        "The test VLAN count must be zero or more.", ["testVlanCount"]
    ))
pc.verifyParameters()

lanA = request.Link("link1", "vlan")
lanB = request.Link("link2", "vlan")
lanTransit = request.Link("link3", "vlan")
lanHostTransit = request.Link("link4", "vlan")
for link, tag in ((lanA, 3811), (lanB, 3812), (lanTransit, 3813), (lanHostTransit, 3814)):
    link.setVlanTag(tag)
    link.link_multiplexing = True
    link.best_effort = True

testLinks = []
for i in range(1, params.testVlanCount + 1):
    link = request.Link("test-vlan-{:02d}".format(i), "vlan")
    link.link_multiplexing = True
    link.best_effort = True
    # CloudLab allocates the tag. SiteRM will configure the host interfaces later.
    testLinks.append(link)

umass = "urn:publicid:IDN+cloudlab.umass.edu+authority+cm"
for i, nodeName in enumerate(nodeList):
    host = request.RawPC(nodeName)
    host.component_manager_id = umass
    host.component_id = nodeName
    host.disk_image = params.osImage

    if params.tempFileSystemSize > 0 or params.tempFileSystemMax:
        bs = host.Blockstore(nodeName + "-bs", params.tempFileSystemMount)
        bs.size = "0GB" if params.tempFileSystemMax else "{}GB".format(params.tempFileSystemSize)
        bs.placement = "any"

    cmd = (
        "sudo /local/repository/post-boot.sh {} {} {} "
        ">> /local/logs/output_log.txt 2>&1"
    ).format(params.workflow, params.toolVersion, params.remoteDesktop)
    host.addService(pg.Execute(shell="bash", command=cmd))

    fpga = request.RawPC("fpga-" + nodeName)
    fpga.component_manager_id = umass
    fpga.component_id = "fpga-" + nodeName
    fpga.setUseTypeDefaultImage()
    fpga.SubNodeOf(host)

    # Reference the same host eth3 interface from each VLAN link.
    host_iface2 = host.addInterface()
    host_iface2.component_id = "eth3"
    localLink = lanA if i == 0 else lanB
    localLink.addInterface(host_iface2)
    lanHostTransit.addInterface(host_iface2)
    for link in testLinks:
        link.addInterface(host_iface2)

    fpga_iface1 = fpga.addInterface()
    fpga_iface1.component_id = "eth0"
    localLink.addInterface(fpga_iface1)

    fpga_iface2 = fpga.addInterface()
    fpga_iface2.component_id = "eth1"
    lanTransit.addInterface(fpga_iface2)

pc.printRequestRSpec(request)
