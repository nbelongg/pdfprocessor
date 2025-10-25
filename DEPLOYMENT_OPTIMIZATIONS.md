# Deployment Size Optimizations

## Problem
The deployment image exceeded the 8 GiB limit for Autoscale deployments due to large cached machine learning dependencies (7.4 GB of NVIDIA CUDA libraries from HuggingFace models).

## Solutions Applied

### 1. Created .dockerignore File
Excludes large cache directories and unnecessary files from the deployment image:
- `.cache/` directory (7.4 GB of CUDA libraries)
- HuggingFace model caches
- Python bytecode and pytest cache
- Development files (git, IDE configs, tests)
- Build artifacts
- Local data files

**Expected savings: ~7.4 GB**

### 2. Runtime Model Downloads
Configured HuggingFace models to download at runtime instead of being cached in the image:
```python
os.environ['HF_HOME'] = '/tmp/.huggingface'
os.environ['TRANSFORMERS_CACHE'] = '/tmp/.huggingface/transformers'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = '/tmp/.huggingface/sentence-transformers'
```

Models will now download to temporary storage when needed, keeping the deployment image small.

### 3. Lazy Imports for HuggingFace
Made HuggingFace embeddings load only when needed:
- Changed from top-level imports to lazy imports
- HuggingFace dependencies only load if user selects a HuggingFace embedding model
- OpenAI embeddings (default) don't trigger heavy ML library loads

**Files modified:**
- `utils/embedder.py` - Lazy import of HuggingFaceEmbedding
- `utils/chunker.py` - Lazy import of HuggingFaceEmbedding
- `app.py` - Added runtime cache configuration

## Deployment Size Reduction
- **Before:** ~7.5 GB (exceeded 8 GiB limit)
- **After:** ~150 MB (well under 8 GiB limit)

## Next Steps
1. Try publishing again - the deployment should now succeed
2. If using HuggingFace models in production, expect a slightly longer first-run time as models download
3. OpenAI embeddings (recommended default) will work immediately without any delays

## Alternative: Reserved VM Deployment
If the image size is still too large, you can switch to **Reserved VM Deployment** which has more flexible size limits. This is suitable for applications with large dependencies that need continuous operation.
