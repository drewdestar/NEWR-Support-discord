const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('whitelist')
        .setDescription('Manage the whitelist for trusted users')
        .addSubcommand(subcommand =>
            subcommand.setName('add')
                .setDescription('Add a user to the whitelist')
                .addUserOption(option =>
                    option.setName('user')
                        .setDescription('The user to add to whitelist')
                        .setRequired(true)
                )
        )
        .addSubcommand(subcommand =>
            subcommand.setName('remove')
                .setDescription('Remove a user from the whitelist')
                .addUserOption(option =>
                    option.setName('user')
                        .setDescription('The user to remove from whitelist')
                        .setRequired(true)
                )
        )
        .addSubcommand(subcommand =>
            subcommand.setName('list')
                .setDescription('List all whitelisted users')
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.Administrator),
    
    async execute(interaction, client, config) {
        const subcommand = interaction.options.getSubcommand();
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.Administrator)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to manage whitelist!', 
                ephemeral: true 
            });
        }
        
        // Get or initialize whitelist for this guild
        let whitelist = client.whitelist.get(interaction.guild.id);
        if (!whitelist) {
            whitelist = [];
            client.whitelist.set(interaction.guild.id, whitelist);
        }
        
        if (subcommand === 'add') {
            const user = interaction.options.getUser('user');
            
            if (whitelist.includes(user.id)) {
                return interaction.reply({ 
                    content: '❌ This user is already whitelisted!', 
                    ephemeral: true 
                });
            }
            
            whitelist.push(user.id);
            client.whitelist.set(interaction.guild.id, whitelist);
            
            // Save whitelist
            saveData('whitelist', client);
            
            const embed = new EmbedBuilder()
                .setColor(0x2ECC71)
                .setTitle('✅ User Added to Whitelist')
                .setDescription(`${user.tag} (${user.id}) has been added to the whitelist!\n\n**Whitelisted users are exempt from:**\n• Anti-spam detection\n• Auto-moderation\n• Invite/link blocking`)
                .setTimestamp();
            
            await interaction.reply({ embeds: [embed] });
            
        } else if (subcommand === 'remove') {
            const user = interaction.options.getUser('user');
            
            const index = whitelist.indexOf(user.id);
            if (index === -1) {
                return interaction.reply({ 
                    content: '❌ This user is not in the whitelist!', 
                    ephemeral: true 
                });
            }
            
            whitelist.splice(index, 1);
            client.whitelist.set(interaction.guild.id, whitelist);
            
            // Save whitelist
            saveData('whitelist', client);
            
            const embed = new EmbedBuilder()
                .setColor(0xFF0000)
                .setTitle('🗑️ User Removed from Whitelist')
                .setDescription(`${user.tag} (${user.id}) has been removed from the whitelist.`)
                .setTimestamp();
            
            await interaction.reply({ embeds: [embed] });
            
        } else if (subcommand === 'list') {
            if (whitelist.length === 0) {
                const embed = new EmbedBuilder()
                    .setColor(0x2ECC71)
                    .setTitle('📋 Whitelist')
                    .setDescription('No users are currently whitelisted.')
                    .setTimestamp();
                
                return interaction.reply({ embeds: [embed] });
            }
            
            // Fetch user details for each whitelisted ID
            const userList = [];
            for (const userId of whitelist) {
                try {
                    const member = await interaction.guild.members.fetch(userId);
                    userList.push(`${member.user.tag} (${userId})`);
                } catch (error) {
                    userList.push(`Unknown User (${userId})`);
                }
            }
            
            const embed = new EmbedBuilder()
                .setColor(0x2ECC71)
                .setTitle('📋 Whitelisted Users')
                .setDescription(userList.join('\n') || 'No users found')
                .addFields({ name: 'Total', value: `${whitelist.length} user(s)`, inline: true })
                .setTimestamp();
            
            await interaction.reply({ embeds: [embed] });
        }
    }
};

// Helper function for saving data
function saveData(collectionName, client) {
    const fs = require('fs');
    const path = require('path');
    const filePath = path.join(__dirname, '..', 'data', `${collectionName}.json`);
    const data = Object.fromEntries(client[collectionName]);
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}
