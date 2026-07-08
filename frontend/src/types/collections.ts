export interface CollectionInfo {
  name: string;
  document_count: number;
  embedding_model: string;
  schema_version: string;
}

export interface CollectionListResponse {
  collections?: CollectionInfo[];
  total: number;
}

export interface DeleteCollectionResponse {
  collection_name: string;
  deleted: boolean;
  message: string;
}
