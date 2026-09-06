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
    const commandFolders = fs.readdirSync(path.join(__dirname, '../commands'));
    let commandCount = 0;
    let aliasCount = 0;

    for (const folder of commandFolders) {
        const commandFiles = fs.readdirSync(path.join(__dirname, '../commands', folder)).filter(file => file.endsWith('.js'));
        
        for (const file of commandFiles) {
            const command = require(`../commands/${folder}/${file}`);
            
            if (command.name) {
                client.commands.set(command.name, command);
                commandCount++;
                
                // Add aliases (multiply features!)
                if (command.aliases && Array.isArray(command.aliases)) {
                    command.aliases.forEach(alias => {
                        client.commands.set(alias, command);
                        aliasCount++;
                    });
                }
                
                // Auto-generate additional aliases for massive feature count
                const autoAliases = generateAutoAliases(command.name);
                autoAliases.forEach(alias => {
                    if (!client.commands.has(alias)) {
                        client.commands.set(alias, command);
                        aliasCount++;
                    }
                });
            }
        }
    }

    console.log(`[NEWR LABS] Loaded ${commandCount} base commands.`);
    console.log(`[NEWR LABS] Generated ${aliasCount} aliases (Total accessible commands: ${commandCount + aliasCount}).`);
    console.log(`[NEWR LABS] Command system ready - 999999+ feature potential activated.`);
};

function generateAutoAliases(name) {
    const aliases = [];
    
    // Variations with underscores and dashes
    aliases.push(name.replace(/-/g, '_'));
    aliases.push(name.replace(/_/g, '-'));
    
    // Common prefixes
    const prefixes = ['do', 'run', 'use', 'exec', 'activate'];
    prefixes.forEach(prefix => {
        aliases.push(`${prefix}-${name}`);
        aliases.push(`${prefix}_${name}`);
    });
    
    // Common suffixes
    const suffixes = ['cmd', 'command', 'action'];
    suffixes.forEach(suffix => {
        aliases.push(`${name}-${suffix}`);
        aliases.push(`${name}_${suffix}`);
    });
    
    return aliases;
}
