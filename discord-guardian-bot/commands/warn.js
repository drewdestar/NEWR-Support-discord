const { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('warn')
        .setDescription('Give a warning to a user')
        .addUserOption(option =>
            option.setName('user')
                .setDescription('The user to warn')
                .setRequired(true)
        )
        .addStringOption(option =>
            option.setName('reason')
                .setDescription('Reason for the warning')
                .setRequired(true)
        )
        .setDefaultMemberPermissions(PermissionFlagsBits.ModerateMembers),
    
    async execute(interaction, client, config) {
        const user = interaction.options.getUser('user');
        const reason = interaction.options.getString('reason');
        
        // Check permissions
        if (!interaction.member.permissions.has(PermissionFlagsBits.ModerateMembers)) {
            return interaction.reply({ 
                content: '❌ You don\'t have permission to warn users!', 
                ephemeral: true 
            });
        }
        
        const member = await interaction.guild.members.fetch(user.id).catch(() => null);
        
        if (!member) {
            return interaction.reply({ 
                content: '❌ User not found in this server!', 
                ephemeral: true 
            });
        }
        
        if (member.id === interaction.user.id) {
            return interaction.reply({ 
                content: '❌ You cannot warn yourself!', 
                ephemeral: true 
            });
        }
        
        if (member.roles.highest.position >= interaction.member.roles.highest.position) {
            return interaction.reply({ 
                content: '❌ You cannot warn someone with a higher or equal role!', 
                ephemeral: true 
            });
        }
        
        // Get or initialize warnings
        const guildWarnings = client.warnings.get(interaction.guild.id) || {};
        const userWarnings = guildWarnings[user.id] || [];
        
        // Add new warning
        userWarnings.push({
            moderator: interaction.user.id,
            moderatorTag: interaction.user.tag,
            reason: reason,
            timestamp: Date.now(),
            id: userWarnings.length + 1
        });
        
        guildWarnings[user.id] = userWarnings;
        client.warnings.set(interaction.guild.id, guildWarnings);
        
        // Save warnings
        saveData('warnings', client);
        
        const embed = new EmbedBuilder()
            .setColor(0xFFA500)
            .setTitle('⚠️ User Warned')
            .addFields(
                { name: 'User', value: `${user.tag} (${user.id})`, inline: true },
                { name: 'Moderator', value: `${interaction.user.tag}`, inline: true },
                { name: 'Warning Count', value: `${userWarnings.length}`, inline: true },
                { name: 'Reason', value: reason, inline: false }
            )
            .setTimestamp()
            .setFooter({ text: `ID: ${user.id}` });
        
        await interaction.reply({ embeds: [embed] });
        
        // DM the user
        try {
            await user.send({
                embeds: [new EmbedBuilder()
                    .setColor(0xFFA500)
                    .setTitle(`⚠️ Warning from ${interaction.guild.name}`)
                    .addFields(
                        { name: 'Reason', value: reason },
                        { name: 'Moderator', value: interaction.user.tag },
                        { name: 'Total Warnings', value: `${userWarnings.length}` }
                    )
                    .setTimestamp()]
            });
        } catch (error) {
            console.log('Could not DM user:', error);
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
