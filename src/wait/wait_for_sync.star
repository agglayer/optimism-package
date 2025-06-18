utils = import_module("../util.star")


def wait_for_sync(plan, l1_config_env_vars):
    plan.run_sh(
        name="wait-for-l1-sync",
        description="Wait for L1 to sync up to network - this can take up to 3days",
        env_vars=l1_config_env_vars,
        run='while true; do sleep 5; \
            metrics=$(curl -s "$L1_METRICS_URL/debug/metrics/prometheus"); \
            el_head_block=$(echo "$metrics" | grep "^chain_head_block "   | awk \'{print $2}\'); \
            el_head_header=$(echo "$metrics" | grep "^chain_head_header " | awk \'{print $2}\'); \
            [ -z "$el_head_block" ] && el_head_block=0; \
            [ -z "$el_head_header" ] && el_head_header=0; \
            sync_distance=$(( el_head_header - el_head_block )); \
            is_optimistic=$(curl -s $CL_RPC_URL/eth/v1/node/syncing | jq -r \'.data.is_optimistic\'); \
            echo "Your L1 is still syncing. Current EL head_block=$el_head_block  head_header=$el_head_header  sync_distance=$sync_distance is_optimistic=$is_optimistic"; \
            if [ "$is_optimistic" == "false" ] || [ $sync_distance -le 0 ]; then echo \'Node is synced!\'; break; fi; done',
        wait="72h",
    )


def wait_for_startup(plan, l1_config_env_vars):
    plan.run_sh(
        name="wait-for-l1-consensus-startup",
        description="Wait for L1 to start up - can take up to 2 minutes",
        image=utils.DEPLOYMENT_UTILS_IMAGE,
        env_vars=l1_config_env_vars,
        run="while true; do sleep 5; echo 'L1 Chain is starting up'; if [ \"$(curl -s $CL_RPC_URL/eth/v1/beacon/headers/ | jq -r '.data[0].header.message.slot')\" != \"0\" ]; then echo 'L1 Chain has started!'; break; fi; done",
        wait="300s",
    )

    # wait for block 3 to avoid transaction indexing in progress errors
    plan.run_sh(
        name="wait-for-l1-execution-startup",
        description="Wait for L1 execution to start up - can take up to 2 minutes",
        image=utils.DEPLOYMENT_UTILS_IMAGE,
        env_vars=l1_config_env_vars,
        run='while true; do sleep 5; current_head=$(cast bn --rpc-url=$L1_RPC_URL); echo "L1 Execution is starting up"; if [ "$current_head" -ge "3" ]; then echo "L1 Execution has started!"; break; fi; done',
        wait="5m",
    )
