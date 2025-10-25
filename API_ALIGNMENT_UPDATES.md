# API Alignment Updates

## Summary
Updated all processing settings to align with LlamaIndex, Pinecone, and OpenAI API specifications.

## Changes Made

### 1. Token-Based Chunking (LlamaIndex TokenTextSplitter)
**Before:**
- Chunk Size: 512 tokens
- Chunk Overlap: 50 tokens

**After (LlamaIndex Defaults):**
- Chunk Size: **1024 tokens** ✓
- Chunk Overlap: **200 tokens** ✓

**Why:** These are the official LlamaIndex defaults and provide better context preservation with the standard 20% overlap ratio.

### 2. Sentence-Based Chunking (LlamaIndex SentenceSplitter)
**Already Correct:**
- Chunk Size: 1024 characters ✓
- Chunk Overlap: 200 characters ✓

**Note:** Both fields are visible and properly labeled with units (characters vs tokens).

### 3. Embedding Dimensions (OpenAI API)
**Updated Auto-Detection:**
- `text-embedding-3-small`: **1536 dimensions** ✓
- `text-embedding-3-large`: **3072 dimensions** ✓
- `text-embedding-ada-002`: **1536 dimensions** ✓

**Improvement:** 
- Embedding dimension field now **auto-updates** when you change models
- Field is **disabled** (read-only) to prevent mismatches
- Tooltip shows correct dimensions for each model

### 4. Pinecone Settings
**Updated Default Environment:**
- Old: `gcp-starter` (pod-based, legacy)
- New: `us-east-1` (serverless, modern)

**Updated Help Text:**
- Now clarifies serverless regions (us-east-1, us-west-2) vs pod environments (gcp-starter)
- Matches current Pinecone best practices

## API Documentation References

### LlamaIndex
- **TokenTextSplitter**: `chunk_size=1024`, `chunk_overlap=200` (default)
- **SentenceSplitter**: `chunk_size=1024`, `chunk_overlap=200` (default)
- Source: https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/

### OpenAI Embeddings
- **text-embedding-3-small**: 1536 dimensions, $0.00002/1K tokens
- **text-embedding-3-large**: 3072 dimensions, $0.00013/1K tokens
- **text-embedding-ada-002**: 1536 dimensions (legacy)
- Source: https://platform.openai.com/docs/guides/embeddings

### Pinecone
- **Dimension Requirement**: Must match embedding model exactly
- **Max Dimensions**: 20,000 for dense vectors
- **Serverless Regions**: us-east-1, us-west-2, eu-west-1, etc.
- Source: https://docs.pinecone.io/guides/indexes/

## Benefits

1. **Better Chunking Quality**
   - 1024 tokens provides better context preservation
   - 200 token overlap (20% ratio) prevents information loss at boundaries

2. **Correct Embedding Dimensions**
   - Auto-detection prevents Pinecone index mismatches
   - Users can't accidentally set wrong dimensions

3. **Modern Pinecone Defaults**
   - Serverless is faster and more cost-effective than pods
   - Better aligns with current Pinecone recommendations

4. **Helpful Tooltips**
   - All fields now have contextual help text
   - References to API defaults included

## Testing Checklist

- [x] Token-based chunking shows correct defaults (1024/200)
- [x] Sentence-based chunking shows correct defaults (1024/200)
- [x] Embedding dimensions auto-update when model changes
- [x] Pinecone environment has modern default (us-east-1)
- [x] All tooltips provide helpful API context
- [x] App runs without errors
