<script lang="ts">
	import { Handle, Position } from '@xyflow/svelte';
	
	let { data } = $props<{ data: { label: string; isProto?: boolean } }>();
</script>

<div class="lang-node">
	<Handle type="target" position={Position.Top} style="visibility: hidden;" />
	<div class="label">{data.label}</div>
	<div class="circle" class:proto={data.isProto}></div>
	<Handle type="source" position={Position.Bottom} style="visibility: hidden;" />
</div>

<style>
	.lang-node {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		pointer-events: all;
	}

	.label {
		color: #e5e7eb;
		font-size: 14px;
		font-weight: 600;
		margin-bottom: 8px;
		text-shadow: 0 2px 4px rgba(0,0,0,0.8);
		white-space: nowrap;
	}

	.circle {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background: rgba(255, 255, 255, 0.1);
		border: 2px solid rgba(255, 255, 255, 0.5);
		backdrop-filter: blur(4px);
		box-shadow: 0 0 15px rgba(255, 255, 255, 0.1);
		transition: all 0.3s ease;
	}

	.circle.proto {
		background: rgba(16, 185, 129, 0.2);
		border-color: #10b981;
		box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
	}

	.circle:hover {
		transform: scale(1.1);
		box-shadow: 0 0 25px rgba(255, 255, 255, 0.3);
	}
</style>
