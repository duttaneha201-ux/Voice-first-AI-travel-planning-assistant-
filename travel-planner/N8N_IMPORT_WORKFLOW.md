# How to Import n8n Workflow JSON

## Quick Import Guide

### Step 1: Download the Workflow File

The workflow file is located at:
```
travel-planner/n8n_workflow.json
```

---

### Step 2: Import into n8n

1. **Open n8n Cloud** (or your n8n instance)
   - Go to: https://app.n8n.cloud/ (or your n8n URL)

2. **Click "Workflows"** in the left sidebar

3. **Click the "+" button** (top right) or **"Import from File"**

4. **Select "Import from File"** or drag and drop

5. **Choose the file:**
   - Navigate to: `travel-planner/n8n_workflow.json`
   - Or copy the JSON content and paste it

6. **Click "Import"**

---

### Step 3: Configure Email Credentials

After importing, you need to set up email credentials:

1. **Click on the "Send Email" node**

2. **Click "Create New Credential"** (or select existing)

3. **Select "SMTP"**

4. **Fill in your email settings:**

   **For Gmail:**
   - **User:** `yourname@gmail.com`
   - **Password:** Your Gmail App Password (not regular password)
   - **Host:** `smtp.gmail.com`
   - **Port:** `587`
   - **Secure:** `TLS`

   **For Outlook:**
   - **User:** `yourname@outlook.com`
   - **Password:** Your Outlook password
   - **Host:** `smtp-mail.outlook.com`
   - **Port:** `587`
   - **Secure:** `TLS`

   **For Other Providers:**
   - Check your email provider's SMTP settings
   - Common ports: `587` (TLS) or `465` (SSL)

5. **Click "Save"**

---

### Step 4: Update Email Address in Workflow

1. **Click on "Send Email" node**

2. **Update "From Email" field:**
   - Change `yourname@gmail.com` to your actual email address

3. **Save the workflow**

---

### Step 5: Activate the Workflow

1. **Click the toggle switch** at the top (should turn green/show "Active")

2. **IMPORTANT:** Workflow must be active to receive webhook requests!

---

### Step 6: Get Webhook URL

1. **Click on "Webhook" node**

2. **Look for "Webhook URLs" section**

3. **Click "Test URL"** button

4. **Copy the URL** shown (starts with `https://`)

5. **Add to your `.env` file:**
   ```env
   N8N_WEBHOOK_URL=https://your-instance.app.n8n.cloud/webhook-test/udaipur-travel-export
   ```

---

## Workflow Structure

The imported workflow includes:

```
┌─────────────┐
│  Webhook    │ ← Receives POST from Streamlit
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ IF: PDF?    │ ← Checks if generate_pdf is true
└──┬──────┬───┘
   │      │
   │ Yes  │ No
   ▼      ▼
┌─────────────┐  ┌──────────────────┐
│ HTML to PDF │  │ Respond to       │
└──────┬──────┘  │ Webhook          │
       │         └──────────────────┘
       ▼
┌─────────────┐
│ IF: Email?  │ ← Checks if send_email is true AND email exists
└──┬──────┬───┘
   │      │
   │ Yes  │ No
   ▼      ▼
┌─────────────┐  ┌──────────────────┐
│ Send Email  │  │ Respond to       │
└──────┬──────┘  │ Webhook          │
       │         └──────────────────┘
       ▼
┌──────────────────┐
│ Respond to       │ ← Returns JSON response
│ Webhook          │
└──────────────────┘
```

---

## What the Workflow Does

1. **Receives webhook** from Streamlit with itinerary data
2. **Checks if PDF should be generated** (`options.generate_pdf`)
3. **Converts HTML to PDF** (if requested)
4. **Checks if email should be sent** (`options.send_email` and `email` exists)
5. **Sends email** with PDF attachment (if requested)
6. **Returns JSON response** with status

---

## Expected Payload from Streamlit

The workflow expects this JSON structure:

```json
{
  "itinerary": {
    "days": [...],
    "metadata": {...},
    "sources": {...},
    "html_content": "<!DOCTYPE html>..."
  },
  "options": {
    "generate_pdf": true,
    "send_email": true
  },
  "email": "user@example.com"
}
```

---

## Response Format

The workflow returns:

```json
{
  "success": true,
  "message": "Itinerary processed successfully",
  "pdf_generated": true,
  "email_sent": true
}
```

---

## Troubleshooting

### Issue 1: "HTML to PDF" node not found

**Solution:**
- n8n Cloud might not have this node
- **Alternative:** Use "Puppeteer" node instead:
  1. Delete "HTML to PDF" node
  2. Add "Puppeteer" node
  3. Configure:
     - **HTML:** `={{ $json.body.itinerary.html_content }}`
     - **Options:** Format A4, Portrait

### Issue 2: Email credentials not working

**Solution:**
- For Gmail: Use **App Password** (not regular password)
- Enable 2-Step Verification first
- Generate App Password at: https://myaccount.google.com/apppasswords

### Issue 3: Webhook URL not showing

**Solution:**
1. Make sure workflow is **saved**
2. Make sure workflow is **active** (toggle ON)
3. Click "Execute Node" on Webhook node
4. URL should appear

### Issue 4: PDF not attaching to email

**Solution:**
- Check "HTML to PDF" node OUTPUT tab
- Verify PDF data is in `{{ $json.binary.data }}`
- If different field name, update "Send Email" node attachments field

---

## Testing the Workflow

### Test 1: PDF Only

1. **Send test request** (using curl, Postman, or your app):
   ```json
   {
     "itinerary": {
       "html_content": "<html><body><h1>Test</h1></body></html>"
     },
     "options": {
       "generate_pdf": true,
       "send_email": false
     }
   }
   ```

2. **Check n8n Executions tab** to see if PDF was generated

### Test 2: Email Only

1. **Send test request:**
   ```json
   {
     "itinerary": {
       "html_content": "<html><body><h1>Test</h1></body></html>"
     },
     "options": {
       "generate_pdf": false,
       "send_email": true
     },
     "email": "your-test@email.com"
   }
   ```

2. **Check your email** to see if it was received

### Test 3: Both PDF and Email

1. **Send test request:**
   ```json
   {
     "itinerary": {
       "html_content": "<html><body><h1>Test</h1></body></html>"
     },
     "options": {
       "generate_pdf": true,
       "send_email": true
     },
     "email": "your-test@email.com"
   }
   ```

2. **Check:**
   - PDF generated in n8n
   - Email received with PDF attachment

---

## Alternative: Using Puppeteer Instead of HTML to PDF

If "HTML to PDF" node is not available:

1. **Delete "HTML to PDF" node**

2. **Add "Puppeteer" node:**
   - Search for "Puppeteer"
   - Configure:
     - **Operation:** "PDF"
     - **HTML:** `={{ $json.body.itinerary.html_content }}`
     - **Options:**
       - Format: A4
       - Orientation: Portrait

3. **Update connections:**
   - Webhook → IF: PDF? → Puppeteer → IF: Email? → Send Email → Respond

---

## Next Steps

1. ✅ Import workflow JSON
2. ✅ Configure email credentials
3. ✅ Update "From Email" address
4. ✅ Activate workflow
5. ✅ Copy webhook URL
6. ✅ Add to `.env` file
7. ✅ Test from Streamlit app

---

## Quick Reference

**File to import:** `travel-planner/n8n_workflow.json`

**After import:**
1. Configure SMTP credentials in "Send Email" node
2. Update "From Email" to your email
3. Activate workflow
4. Copy webhook URL to `.env`

**Test:** Generate itinerary in Streamlit → Click "📄 Generate PDF" or "📧 Email Itinerary"

---

Good luck! 🚀
