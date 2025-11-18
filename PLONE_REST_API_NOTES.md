# Plone REST API - Subject Field Update Notes

## Issue
When trying to update the `subjects` field via PATCH, we're getting a `__getitem__` AttributeError (500 status).

## Current Understanding

Based on Plone REST API documentation:
- PATCH requests should work with field names directly: `{"field_name": value}`
- The Subject field in Plone is a special field (KeywordIndex)
- Some Plone REST API versions may handle Subject differently

## What We've Tried

1. `{"Subject": subjects}` - Standard Plone field name (capital S)
2. `{"subjects": subjects}` - Lowercase as it appears in response
3. `{"subjects": tuple(subjects)}` - Matching tuple format
4. `@content` endpoint - Not available (404)
5. `@fields/subject` endpoint - Not available (404)
6. Full item update - Same error
7. POST to @content - Not available (404)

## Error Analysis

The `__getitem__` AttributeError suggests:
- Server-side code is trying to access `data['some_key']` 
- But `data` is not a dict or doesn't have that key
- This could be a serializer issue on the server side

## Possible Causes

1. **Custom Serializer**: The site might have a custom serializer that expects a different format
2. **API Version**: Older/newer Plone REST API versions might handle Subject differently
3. **Field Not Updatable**: Subject field might not be updatable via REST API on this site
4. **Permissions**: Might need different permissions (though we're authenticated)
5. **Content Type**: The content type might not support Subject updates via REST

## Next Steps

1. Check Plone REST API version on the server
2. Inspect the actual request being sent (add request logging)
3. Check if there's a schema endpoint that shows field definitions
4. Try updating a different field (like title) to confirm PATCH works
5. Check Plone REST API GitHub issues for similar problems

## References

- [Plone REST API Documentation](https://6.docs.plone.org/plone.restapi/docs/source/index.html)
- [Plone REST API Endpoints](https://plonerestapi.readthedocs.io/en/latest/endpoints/index.html)
- [Plone REST API Usage](https://plonerestapi.readthedocs.io/en/latest/usage/index.html)


