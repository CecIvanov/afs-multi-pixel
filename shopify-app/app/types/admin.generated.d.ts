/* eslint-disable eslint-comments/disable-enable-pair */
/* eslint-disable eslint-comments/no-unlimited-disable */
/* eslint-disable */
import type * as AdminTypes from './admin.types.js';

export type MultiPixelMarketsQueryVariables = AdminTypes.Exact<{ [key: string]: never; }>;


export type MultiPixelMarketsQuery = { markets: { nodes: Array<Pick<AdminTypes.Market, 'id' | 'name' | 'handle' | 'status'>> } };

export type MultiPixelInstallationQueryVariables = AdminTypes.Exact<{ [key: string]: never; }>;


export type MultiPixelInstallationQuery = { currentAppInstallation: Pick<AdminTypes.AppInstallation, 'id'> };

export type MultiPixelSetMappingMutationVariables = AdminTypes.Exact<{
  metafields: Array<AdminTypes.MetafieldsSetInput> | AdminTypes.MetafieldsSetInput;
}>;


export type MultiPixelSetMappingMutation = { metafieldsSet?: AdminTypes.Maybe<{ userErrors: Array<Pick<AdminTypes.MetafieldsSetUserError, 'field' | 'message'>> }> };

export type MultiPixelUpdateWebPixelMutationVariables = AdminTypes.Exact<{
  id: AdminTypes.Scalars['ID']['input'];
  webPixel: AdminTypes.WebPixelInput;
}>;


export type MultiPixelUpdateWebPixelMutation = { webPixelUpdate?: AdminTypes.Maybe<{ userErrors: Array<Pick<AdminTypes.ErrorsWebPixelUserError, 'field' | 'message'>> }> };

export type MultiPixelCreateWebPixelMutationVariables = AdminTypes.Exact<{
  webPixel: AdminTypes.WebPixelInput;
}>;


export type MultiPixelCreateWebPixelMutation = { webPixelCreate?: AdminTypes.Maybe<{ userErrors: Array<Pick<AdminTypes.ErrorsWebPixelUserError, 'field' | 'message'>> }> };

export type MultiPixelWebPixelQueryVariables = AdminTypes.Exact<{ [key: string]: never; }>;


export type MultiPixelWebPixelQuery = { webPixel?: AdminTypes.Maybe<Pick<AdminTypes.WebPixel, 'id'>> };

interface GeneratedQueryTypes {
  "#graphql\n      query multiPixelMarkets {\n        markets(first: 100) {\n          nodes {\n            id\n            name\n            handle\n            status\n          }\n        }\n      }": {return: MultiPixelMarketsQuery, variables: MultiPixelMarketsQueryVariables},
  "#graphql\n      query multiPixelInstallation {\n        currentAppInstallation {\n          id\n        }\n      }": {return: MultiPixelInstallationQuery, variables: MultiPixelInstallationQueryVariables},
  "#graphql\n        query multiPixelWebPixel {\n          webPixel {\n            id\n          }\n        }": {return: MultiPixelWebPixelQuery, variables: MultiPixelWebPixelQueryVariables},
}

interface GeneratedMutationTypes {
  "#graphql\n      mutation multiPixelSetMapping($metafields: [MetafieldsSetInput!]!) {\n        metafieldsSet(metafields: $metafields) {\n          userErrors {\n            field\n            message\n          }\n        }\n      }": {return: MultiPixelSetMappingMutation, variables: MultiPixelSetMappingMutationVariables},
  "#graphql\n        mutation multiPixelUpdateWebPixel($id: ID!, $webPixel: WebPixelInput!) {\n          webPixelUpdate(id: $id, webPixel: $webPixel) {\n            userErrors {\n              field\n              message\n            }\n          }\n        }": {return: MultiPixelUpdateWebPixelMutation, variables: MultiPixelUpdateWebPixelMutationVariables},
  "#graphql\n      mutation multiPixelCreateWebPixel($webPixel: WebPixelInput!) {\n        webPixelCreate(webPixel: $webPixel) {\n          userErrors {\n            field\n            message\n          }\n        }\n      }": {return: MultiPixelCreateWebPixelMutation, variables: MultiPixelCreateWebPixelMutationVariables},
}
declare module '@shopify/admin-api-client' {
  type InputMaybe<T> = AdminTypes.InputMaybe<T>;
  interface AdminQueries extends GeneratedQueryTypes {}
  interface AdminMutations extends GeneratedMutationTypes {}
}
