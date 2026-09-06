/**
 * Event Handler - Load All Events
 * 
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY is the parent company (like Meta)
 * NEWR LABS is the development studio/brand (like Instagram under Meta)
 * ────────────────────────────────────────────────────────
 * 
 * Author: NEWR LABS Core Team
 * Company: NEWROPLY
 * License: Proprietary - NEWROPLY
 * 
 * ⚠️ This event system is property of NEWROPLY.
 * Unauthorized use is strictly prohibited.
 * ────────────────────────────────────────────────────────
 */

const fs = require('fs');
const path = require('path');

module.exports = (client) => {
    console.log('📡 Event Handler initialized - Powered by NEWR LABS');
    console.log('© 2024 NEWROPLY - All Rights Reserved');
    
    const eventPath = path.join(__dirname, '../events');
    
    if (!fs.existsSync(eventPath)) {
        fs.mkdirSync(eventPath, { recursive: true });
        console.log('📁 Created events folder');
        return;
    }
    
    const eventFiles = fs.readdirSync(eventPath).filter(file => file.endsWith('.js'));
    
    for (const file of eventFiles) {
        const filePath = path.join(eventPath, file);
        const event = require(filePath);
        
        if (event.name && event.execute) {
            if (event.once) {
                client.once(event.name, (...args) => event.execute(...args, client));
            } else {
                client.on(event.name, (...args) => event.execute(...args, client));
            }
            console.log(`✅ Loaded event: ${file}`);
        } else {
            console.warn(`⚠️  Skipping ${file}: Missing name or execute function`);
        }
    }
};
