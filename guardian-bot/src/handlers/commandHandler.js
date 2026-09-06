/**
 * Command Handler - Load All Commands
 * 
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY is the parent company (like Meta)
 * NEWR LABS is the development studio/brand (like Instagram under Meta)
 * ────────────────────────────────────────────────────────
 * 
 * Author: NEWR LABS Development Team
 * Company: NEWROPLY
 * License: Proprietary - NEWROPLY
 * 
 * ⚠️ This command system is property of NEWROPLY.
 * Unauthorized use is strictly prohibited.
 * ────────────────────────────────────────────────────────
 */

const fs = require('fs');
const path = require('path');

module.exports = (client) => {
    console.log('⚙️ Command Handler initialized - Powered by NEWR LABS');
    console.log('© 2024 NEWROPLY - All Rights Reserved');
    
    const commandFolders = ['moderation', 'security', 'utility', 'economy', 'level', 'ticket', 'giveaway', 'config', 'owner'];
    
    for (const folder of commandFolders) {
        const commandPath = path.join(__dirname, '../commands', folder);
        if (!fs.existsSync(commandPath)) {
            fs.mkdirSync(commandPath, { recursive: true });
            console.log(`📁 Created commands/${folder} folder`);
            continue;
        }
        
        const commandFiles = fs.readdirSync(commandPath).filter(file => file.endsWith('.js'));
        
        for (const file of commandFiles) {
            const filePath = path.join(commandPath, file);
            const command = require(filePath);
            
            if (command.name && typeof command.execute === 'function') {
                client.commands.set(command.name, command);
                console.log(`✅ Loaded command: ${folder}/${file}`);
                
                if (command.aliases && Array.isArray(command.aliases)) {
                    for (const alias of command.aliases) {
                        client.commands.set(alias, command);
                    }
                }
            } else {
                console.warn(`⚠️  Skipping ${file}: Missing name or execute function`);
            }
        }
    }
    
    console.log(`📦 Total commands loaded: ${client.commands.size}`);
};
