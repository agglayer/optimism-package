NETWORK_NAME = "kurtosis"

HTTP_PORT_ID = "http"
RPC_PORT_ID = "rpc"
WS_PORT_ID = "ws"
TCP_DISCOVERY_PORT_ID = "tcp-discovery"
UDP_DISCOVERY_PORT_ID = "udp-discovery"
ENGINE_RPC_PORT_ID = "engine-rpc"
ENGINE_WS_PORT_ID = "engineWs"

EL_TYPE = struct(
    op_geth="op-geth",
    op_erigon="op-erigon",
    op_nethermind="op-nethermind",
    op_besu="op-besu",
    op_rbuilder="op-rbuilder",
    op_reth="op-reth",
)

CL_TYPE = struct(
    op_node="op-node",
    hildr="hildr",
    kona_node="kona-node",
)

CLIENT_TYPES = struct(
    el="execution",
    cl="beacon",
)
VOLUME_SIZE = {
    "kurtosis": {
        "op-geth_volume_size": 5000,  # 5GB
        "op-erigon_volume_size": 3000,  # 3GB
        "op-nethermind_volume_size": 3000,  # 3GB
        "op-besu_volume_size": 3000,  # 3GB
        "op-rbuilder_volume_size": 3000,  # 3GB
        "op-reth_volume_size": 3000,  # 3GB
        "op-node_volume_size": 1000,  # 1GB
        "hildr_volume_size": 1000,  # 1GB
        "kona-node_volume_size": 1000,  # 1GB
    },
}

dev_accounts = [
    {
        "address": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "private_key": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    },
    {
        "address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "private_key": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    },
    {
        "address": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        "private_key": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    },
    {
        "address": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
        "private_key": "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    },
    {
        "address": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
        "private_key": "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    },
    {
        "address": "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",
        "private_key": "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    },
    {
        "address": "0x976EA74026E726554dB657fA54763abd0C3a0aa9",
        "private_key": "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    },
    {
        "address": "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",
        "private_key": "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
    },
    {
        "address": "0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f",
        "private_key": "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
    },
    {
        "address": "0xa0Ee7A142d267C1f36714E4a8F75612F20a79720",
        "private_key": "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
    },
]

mnemonic = "test test test test test test test test test test test junk"

# op-deployer v0.10.0 needs an SP1 verifier exposing VERSION() on the L1. Devnets never submit
# ZK proofs, so the L1 genesis preloads Optimism's MockSP1Verifier (runtime code) at this address.
MOCK_SP1_VERIFIER_ADDRESS = "0x5100000000000000000000000000000000000001"
MOCK_SP1_VERIFIER_CODE = "0x608060405234801561001057600080fd5b50600436106100415760003560e01c80632a5104361461004657806341493c6014610079578063ffa1ad7414610090575b600080fd5b6040517f0d13b26f3ea578005da0af16c31e23911e3f8f5124005a1e77fa2a6477dc930e81526020015b60405180910390f35b61008e610087366004610118565b5050505050565b005b604080518082018252600b81527f76302e302e302d4d4f434b000000000000000000000000000000000000000000602082015290516100709190610192565b60008083601f8401126100e157600080fd5b50813567ffffffffffffffff8111156100f957600080fd5b60208301915083602082850101111561011157600080fd5b9250929050565b60008060008060006060868803121561013057600080fd5b85359450602086013567ffffffffffffffff8082111561014f57600080fd5b61015b89838a016100cf565b9096509450604088013591508082111561017457600080fd5b50610181888289016100cf565b969995985093965092949392505050565b600060208083528351808285015260005b818110156101bf578581018301518582016040015282016101a3565b818111156101d1576000604083870101525b50601f017fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffe01692909201604001939250505056fea164736f6c634300080f000a"
