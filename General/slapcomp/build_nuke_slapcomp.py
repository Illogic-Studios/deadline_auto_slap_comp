import json
import os 
import nuke

def main():
    with open(os.environ["SLAPCOMP_DATA"]) as f:
        data = json.load(f)

    nuke.scriptClear()
    root = nuke.toNode("root")
    root.knob("colorManagement").setValue("OCIO")
    root.knob("OCIO_config").setValue("custom")
    root.knob("customOCIOConfigPath").setValue(data["ocio_config"])

    read_nodes = []
    for idx, layer in enumerate(data["layers"]):
        r = nuke.createNode("Read", inpanel=False)
        r.knob("file").setValue(layer["path"])
        r.knob("first").setValue(layer["first_frame"])
        r.knob("last").setValue(layer["last_frame"])
        r.knob("origfirst").setValue(layer["first_frame"])
        r.knob("origlast").setValue(layer["last_frame"])
        r.knob("label").setValue(layer["layer_name"])
        r.setXYpos(idx * 200, 0)
        read_nodes.append(r)

    current = read_nodes[0]
    y = 150
    for layer, node in zip(data["layers"][1:], read_nodes[1:]):
        m = nuke.createNode("Merge2", inpanel=False)
        m.knob("operation").setValue(layer.get("merge_operation", "over"))
        m.setInput(0, current)
        m.setInput(1, node)
        m.setXYpos(0, y)
        current, y = m, y + 100

    write = nuke.createNode("Write", inpanel=False)
    write.knob("file").setValue(data["render_dir"])
    write.knob("file_type").setValue("exr")
    write.knob("compression").setValue("DWAB")
    write.knob("channels").setValue("rgba")
    write.knob("create_directories").setValue(True)
    write.setInput(0, current)

    nuke.scriptSaveAs(data["output_nk"], overwrite=1)

if __name__ == "__main__":
    main()