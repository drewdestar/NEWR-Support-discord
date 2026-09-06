/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY: Parent Company
 * NEWR LABS: Division responsible for Code, App, Software Development
 * ────────────────────────────────────────────────────────
 */

const fs = require('fs');
const path = require('path');

module.exports = (client) => {
    const eventFiles = fs.readdirSync(path.join(__dirname, '../events')).filter(file => file.endsWith('.js'));
    
    for (const file of eventFiles) {
        const event = require(`../events/${file}`);
        if (event.once) {
            client.once(event.name, (...args) => event.execute(...args, client));
        } else {
            client.on(event.name, (...args) => event.execute(...args, client));
        }
    }
    
    console.log(`[NEWR LABS] Loaded ${eventFiles.length} event handlers.`);
};
